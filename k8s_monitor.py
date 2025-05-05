import os
import time
import logging
import smtplib
import threading
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from kubernetes import client, config, watch
from kubernetes.client.rest import ApiException

# Import database models
try:
    from models import db, Alert, app
    DB_AVAILABLE = True
    logger = logging.getLogger(__name__)
    logger.info("Database available for alert persistence")
except ImportError:
    DB_AVAILABLE = False
    logger = logging.getLogger(__name__)
    logger.warning("Database models not available, alerts will not be persisted")

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Import mock data for development/demo environment
try:
    from mock_k8s_data import get_mock_nodes, get_mock_pods
    MOCK_DATA_AVAILABLE = True
    logger.info("Mock data module loaded for development/demo environment")
except ImportError:
    MOCK_DATA_AVAILABLE = False
    logger.warning("Mock data module not available, will try to use real Kubernetes API")

# Configuration
POLL_INTERVAL = int(os.environ.get('POLL_INTERVAL', '60'))  # seconds
ALERT_COOL_DOWN = int(os.environ.get('ALERT_COOL_DOWN', '300'))  # seconds, avoid alert spam

# SMTP Configuration
SMTP_SERVER = os.environ.get('SMTP_SERVER')
SMTP_PORT = int(os.environ.get('SMTP_PORT', '587'))
SMTP_USERNAME = os.environ.get('SMTP_USERNAME')
SMTP_PASSWORD = os.environ.get('SMTP_PASSWORD')
EMAIL_FROM = os.environ.get('EMAIL_FROM')
EMAIL_TO = os.environ.get('EMAIL_TO', '').split(',')
EMAIL_SUBJECT_PREFIX = os.environ.get('EMAIL_SUBJECT_PREFIX', '[K8s Alert]')

# Alert state tracking
# Do not use sent_alerts for UI updates to avoid data format inconsistencies
# sent_alerts is only for tracking cool down periods
sent_alerts = {}  
node_statuses = {}
pod_statuses = {}

class KubernetesMonitor:
    def __init__(self):
        self.setup_kubernetes_client()
        
    def setup_kubernetes_client(self):
        """Set up the Kubernetes client based on the environment"""
        try:
            # When running in cluster
            config.load_incluster_config()
            logger.info("Loaded in-cluster configuration")
        except config.ConfigException:
            # When running outside of the cluster (for development)
            try:
                config.load_kube_config()
                logger.info("Loaded kubeconfig file")
            except config.ConfigException:
                # For local development/demo, use mock data
                logger.warning("Could not configure kubernetes client, using mock data mode")
                # We'll continue without raising an exception

        # Initialize API clients
        self.core_v1 = client.CoreV1Api()
        self.apps_v1 = client.AppsV1Api()
    
    def send_email_alert(self, subject, message):
        """Send an email alert"""
        if not all([SMTP_SERVER, SMTP_USERNAME, SMTP_PASSWORD, EMAIL_FROM, EMAIL_TO]):
            logger.warning("SMTP configuration incomplete. Cannot send email.")
            return False
        
        try:
            msg = MIMEMultipart()
            msg['From'] = EMAIL_FROM
            msg['To'] = ', '.join(EMAIL_TO)
            msg['Subject'] = f"{EMAIL_SUBJECT_PREFIX} {subject}"
            
            msg.attach(MIMEText(message, 'plain'))
            
            with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
                server.starttls()
                server.login(SMTP_USERNAME, SMTP_PASSWORD)
                server.send_message(msg)
                
            logger.info(f"Email alert sent: {subject}")
            return True
        except Exception as e:
            logger.error(f"Failed to send email: {str(e)}")
            return False
    
    def check_can_send_alert(self, alert_key):
        """Check if we should send an alert or if we're in cool down period"""
        current_time = time.time()
        
        # Sık uyarıları engellemek için soğuma süresi kontrolü
        if alert_key in sent_alerts:
            if current_time - sent_alerts[alert_key] < ALERT_COOL_DOWN:
                return False
        
        # Uyarı gönderim zamanını kaydet
        sent_alerts[alert_key] = current_time
        
        # Veritabanı mevcutsa, uyarıyı veritabanına kaydet
        if DB_AVAILABLE:
            try:
                # Parse alert key to get details
                parts = alert_key.split(':')
                resource_type = parts[0]
                resource_name = parts[1]
                
                # Namespace/pod_name formatındaki resource_name'i ayır
                if '/' in resource_name:
                    namespace, pod_name = resource_name.split('/', 1)
                else:
                    namespace = None
                    pod_name = resource_name
                
                status = parts[2] if len(parts) > 2 else 'Unknown'
                
                if 'Recovery' in status or 'ContainerRecovery' in status:
                    # İyileşme ise, ilgili uyarıları çözüldü olarak işaretle
                    with app.app_context():
                        # Query oluştur - Sadece belirli bir resource için
                        query = Alert.query.filter(
                            Alert.resource_type == resource_type,
                            Alert.resource_name == pod_name,
                            Alert.is_resolved == 0
                        )
                        
                        # Namespace varsa filtreye ekle
                        if namespace:
                            query = query.filter(Alert.resource_namespace == namespace)
                        
                        # Alarmları getir
                        existing_alerts = query.all()
                        
                        # Alarmları çözüldü olarak işaretle
                        for alert in existing_alerts:
                            alert.resolve()
                        
                        # Kaydetmeyi tamamla
                        if existing_alerts:
                            db.session.commit()
                            logger.info(f"Marked {len(existing_alerts)} alerts as resolved for {resource_name}")
                            
                        # İyileşme bildirimi için yeni bir alarm oluştur
                        recovery_alert = Alert(
                            alert_key=alert_key,
                            resource_type=resource_type,
                            resource_name=pod_name,
                            resource_namespace=namespace,
                            status=status,
                            message=f"{resource_type} '{pod_name}' has recovered from {status.replace('Recovery', '').replace('ContainerRecovery', '')} state at {time.strftime('%Y-%m-%d %H:%M:%S')}"
                        )
                        db.session.add(recovery_alert)
                        db.session.commit()
                        logger.info(f"Created recovery alert in database: {alert_key}")
                else:
                    # Zaten çözülmüş bir alarm için yeni alarm göndermeyi engelle
                    with app.app_context():
                        # Son 1 saat içinde çözülmüş benzer bir alarm var mı kontrol et
                        one_hour_ago = time.time() - 3600
                        # SQLite için UNIX timestamp'ten datetime oluşturmak
                        from sqlalchemy.sql import func
                        one_hour_ago_dt = func.datetime(one_hour_ago, 'unixepoch')
                        recent_resolved = Alert.query.filter(
                            Alert.resource_type == resource_type,
                            Alert.resource_name == pod_name,
                            Alert.is_resolved == 1,
                            Alert.resolved_at > one_hour_ago_dt
                        )
                        
                        if namespace:
                            recent_resolved = recent_resolved.filter(Alert.resource_namespace == namespace)
                        
                        # Eğer son bir saat içinde çözülmüş bir alarm varsa ve şimdi aynı sorun tekrar ortaya çıktıysa
                        # bu yinelenen bir sorun olabilir, bu durumda uyarı göndermeye devam et
                        
                        # Aynı key ile aktif bir alarm zaten var mı kontrol et
                        # Varsa yeni bir alarm oluşturmayız
                        active_alert = Alert.query.filter(
                            Alert.alert_key == alert_key,
                            Alert.is_resolved == 0
                        ).first()
                        
                        if not active_alert:
                            # Yeni alarm
                            alert = Alert(
                                alert_key=alert_key,
                                resource_type=resource_type,
                                resource_name=pod_name,
                                resource_namespace=namespace,
                                status=status,
                                message=f"Alert triggered for {resource_type} '{pod_name}' with status: {status} at {time.strftime('%Y-%m-%d %H:%M:%S')}"
                            )
                            db.session.add(alert)
                            db.session.commit()
                            logger.info(f"Saved alert to database: {alert_key}")
                        else:
                            logger.info(f"Alert already exists and is active: {alert_key}")
                            # Aktif uyarı durumunda soğuma süresini sıfırla ama yeni uyarı oluşturma
                            return False
            except Exception as e:
                logger.error(f"Failed to save alert to database: {str(e)}")
        
        return True
    
    def monitor_nodes(self):
        """Monitor Kubernetes nodes for issues"""
        try:
            # Aktif node'ları sakla
            active_nodes = set()
            
            try:
                nodes = self.core_v1.list_node().items
            except Exception as e:
                logger.warning(f"Failed to get nodes from Kubernetes API: {e}")
                if MOCK_DATA_AVAILABLE:
                    nodes = get_mock_nodes()
                    logger.info("Using mock node data for monitoring")
                else:
                    nodes = []
                    logger.error("No mock data available and Kubernetes API unreachable")
            
            for node in nodes:
                node_name = node.metadata.name
                node_status = "Ready"
                
                # Aktif node listesine ekle
                active_nodes.add(node_name)
                
                # Check node conditions
                for condition in node.status.conditions:
                    if condition.type == "Ready" and condition.status != "True":
                        node_status = "NotReady"
                        
                        # Check if we should send an alert
                        alert_key = f"node:{node_name}:NotReady"
                        # Ayrıntılı hata mesajı
                        detailed_message = f"""
                        Kubernetes Node Alert: {node_name} is NotReady
                        
                        Node: {node_name}
                        Status: NotReady
                        Reason: {condition.reason}
                        Message: {condition.message}
                        Last Transition: {condition.last_transition_time}
                        """
                        
                        if self.check_can_send_alert(alert_key):
                            # E-posta bildirimi gönder
                            self.send_email_alert(f"Node {node_name} is NotReady", detailed_message)
                            
                            # Hata mesajını veritabanındaki uyarıda güncelle
                            if DB_AVAILABLE:
                                with app.app_context():
                                    alert = Alert.query.filter_by(alert_key=alert_key, is_resolved=0).first()
                                    if alert:
                                        alert.message = f"Node NotReady: {condition.reason} - {condition.message}"
                                        db.session.commit()
                
                # Update our node status record
                previous_status = node_statuses.get(node_name)
                node_statuses[node_name] = node_status
                
                # If node recovered, send recovery alert and resolve alerts
                if previous_status == "NotReady" and node_status == "Ready":
                    alert_key = f"node:{node_name}:Recovery"
                    if self.check_can_send_alert(alert_key):
                        message = f"""
                        Kubernetes Node Recovery: {node_name} is Ready
                        
                        Node: {node_name}
                        Status: Ready
                        """
                        self.send_email_alert(f"Node {node_name} recovered", message)
                        
                        # Alarmı çözme işlemi check_can_send_alert içinde yapılıyor
            
            # Silinmiş node'ları kontrol et ve alarmlarını çöz
            if DB_AVAILABLE:
                for old_node in list(node_statuses.keys()):
                    if old_node not in active_nodes:
                        # Node artık mevcut değil, tüm alarmları çöz
                        with app.app_context():
                            # Mevcut alarmları bul
                            existing_alerts = Alert.query.filter(
                                Alert.resource_type == "node",
                                Alert.resource_name == old_node,
                                Alert.is_resolved == 0
                            ).all()
                            
                            # Alarmları çözüldü olarak işaretle
                            for alert in existing_alerts:
                                alert.resolve()
                            
                            # Kaydetmeyi tamamla
                            if existing_alerts:
                                db.session.commit()
                                logger.info(f"Marked {len(existing_alerts)} alerts as resolved for deleted node {old_node}")
                        
                        # Node durumunu takip listesinden kaldır
                        node_statuses.pop(old_node, None)
                        logger.info(f"Removed tracking for deleted node: {old_node}")
            
            logger.info(f"Monitored {len(nodes)} nodes")
        except ApiException as e:
            logger.error(f"Error monitoring nodes: {e}")
    
    def monitor_pods(self):
        """Monitor Kubernetes pods for issues"""
        try:
            # Aktif pod'ları takip etmek için
            active_pods = set()
            
            try:
                pods = self.core_v1.list_pod_for_all_namespaces().items
            except Exception as e:
                logger.warning(f"Failed to get pods from Kubernetes API: {e}")
                if MOCK_DATA_AVAILABLE:
                    pods = get_mock_pods()
                    logger.info("Using mock pod data for monitoring")
                else:
                    logger.error("No mock data available and Kubernetes API unreachable")
                    return
            
            for pod in pods:
                pod_name = pod.metadata.name
                namespace = pod.metadata.namespace
                pod_key = f"{namespace}/{pod_name}"
                
                # Aktif pod listesine ekle
                active_pods.add(pod_key)
                
                # Skip monitoring specific system pods if needed
                # if namespace == "kube-system" and any(pod_name.startswith(prefix) for prefix in ["calico-", "kube-proxy-"]):
                #     continue
                
                phase = pod.status.phase
                container_statuses = pod.status.container_statuses or []
                
                # Check for problematic pod phases
                if phase in ["Failed", "Pending"]:
                    alert_key = f"pod:{pod_key}:{phase}"
                    
                    # Ayrıntılı hata mesajı
                    detailed_message = f"""
                    Kubernetes Pod Alert: {pod_key} is in {phase} state
                    
                    Pod: {pod_name}
                    Namespace: {namespace}
                    Phase: {phase}
                    Reason: {getattr(pod.status, 'reason', 'Not available')}
                    Message: {getattr(pod.status, 'message', 'Not available')}
                    """
                    
                    if self.check_can_send_alert(alert_key):
                        # E-posta bildirimi gönder
                        self.send_email_alert(f"Pod {pod_name} is {phase}", detailed_message)
                        
                        # Hata mesajını veritabanındaki uyarıda güncelle
                        if DB_AVAILABLE:
                            with app.app_context():
                                alert = Alert.query.filter_by(alert_key=alert_key, is_resolved=0).first()
                                if alert:
                                    alert.message = f"Pod {phase}: {getattr(pod.status, 'reason', 'Unknown reason')} - {getattr(pod.status, 'message', 'No details')}"
                                    db.session.commit()
                
                # Check for container restart issues
                for container in container_statuses:
                    container_name = container.name
                    restart_count = container.restart_count
                    
                    if restart_count > 5:
                        alert_key = f"pod:{pod_key}:{container_name}:restarts"
                        if self.check_can_send_alert(alert_key):
                            message = f"""
                            Kubernetes Container Alert: {container_name} in pod {pod_key} has restarted {restart_count} times
                            
                            Pod: {pod_name}
                            Namespace: {namespace}
                            Container: {container_name}
                            Restart Count: {restart_count}
                            """
                            self.send_email_alert(f"Container {container_name} has excessive restarts", message)
                    
                    # Konteyner durum kontrolü (Waiting durumundaysa)
                    if (container.state.waiting and 
                        hasattr(container.state.waiting, 'reason')):
                        
                        wait_reason = container.state.waiting.reason
                        wait_message = getattr(container.state.waiting, 'message', 'No message')
                        
                        # Çeşitli bekleme durumlarını kontrol et
                        if wait_reason in ["CrashLoopBackOff", "ImagePullBackOff", "ErrImagePull", 
                                          "CreateContainerConfigError", "CreateContainerError"]:
                            
                            alert_key = f"pod:{pod_key}:{container_name}:{wait_reason}"
                            
                            # Ayrıntılı hata mesajı
                            detailed_message = f"""
                            Kubernetes Container Alert: {container_name} in pod {pod_key} is in {wait_reason}
                            
                            Pod: {pod_name}
                            Namespace: {namespace}
                            Container: {container_name}
                            Status: {wait_reason}
                            Message: {wait_message}
                            """
                            
                            if self.check_can_send_alert(alert_key):
                                # E-posta bildirimi gönder
                                self.send_email_alert(f"Container {container_name} is in {wait_reason}", detailed_message)
                                
                                # Hata mesajını veritabanındaki uyarıda güncelle
                                if DB_AVAILABLE:
                                    with app.app_context():
                                        alert = Alert.query.filter_by(alert_key=alert_key, is_resolved=0).first()
                                        if alert:
                                            alert.message = f"Container {wait_reason}: {wait_message}"
                                            db.session.commit()
                
                # Önceki pod durumunu kontrol et
                previous_pod_status = pod_statuses.get(pod_key, {})
                
                # Geçerli tüm konteyner durumlarını topla
                container_details = {}
                for container in container_statuses:
                    container_name = container.name
                    
                    # Konteyner durumunu belirle
                    if container.state.running:
                        container_state = "Running"
                        reason = ""
                    elif container.state.waiting and hasattr(container.state.waiting, 'reason'):
                        container_state = "Waiting"
                        reason = container.state.waiting.reason
                    elif container.state.terminated:
                        container_state = "Terminated"
                        reason = getattr(container.state.terminated, 'reason', "")
                    else:
                        container_state = "Unknown"
                        reason = ""
                    
                    container_details[container_name] = {
                        "state": container_state,
                        "reason": reason,
                        "ready": container.ready
                    }
                
                # Güncel durumu kaydet
                current_pod_status = {
                    "phase": phase,
                    "containers": container_details
                }
                
                # Pod durumunu güncelle
                pod_statuses[pod_key] = current_pod_status
                
                # İyileşme durumunu kontrol et (Pod Running durumuna geçtiyse)
                if (phase == "Running" and 
                    previous_pod_status.get("phase") in ["Failed", "Pending"]):
                    
                    alert_key = f"pod:{pod_key}:Recovery"
                    if self.check_can_send_alert(alert_key):
                        message = f"""
                        Kubernetes Pod Recovery: {pod_key} is now Running
                        
                        Pod: {pod_name}
                        Namespace: {namespace}
                        Previous Status: {previous_pod_status.get("phase", "Unknown")}
                        Current Status: Running
                        """
                        self.send_email_alert(f"Pod {pod_name} recovered", message)
                
                # Konteyner iyileşmelerini kontrol et
                for container_name, container_info in container_details.items():
                    # Önceki konteyner durumunu al
                    prev_containers = previous_pod_status.get("containers", {})
                    prev_container_info = prev_containers.get(container_name, {})
                    
                    # Eğer konteyner bir hata durumundan Running durumuna geçtiyse
                    if (container_info["state"] == "Running" and 
                        prev_container_info.get("state") == "Waiting" and
                        prev_container_info.get("reason") in ["ImagePullBackOff", "CrashLoopBackOff", 
                                                           "ErrImagePull", "CreateContainerError"]):
                        
                        alert_key = f"pod:{pod_key}:{container_name}:ContainerRecovery"
                        if self.check_can_send_alert(alert_key):
                            message = f"""
                            Kubernetes Container Recovery: {container_name} in pod {pod_key} is now Running
                            
                            Pod: {pod_name}
                            Namespace: {namespace}
                            Container: {container_name}
                            Previous Status: {prev_container_info.get("reason", "Unknown")}
                            Current Status: Running
                            """
                            self.send_email_alert(f"Container {container_name} recovered", message)
            
            # Silinmiş pod'ları kontrol et ve alarmlarını çöz
            if DB_AVAILABLE:
                for old_pod_key in list(pod_statuses.keys()):
                    if old_pod_key not in active_pods:
                        # Pod artık mevcut değil, tüm alarmları çözelim
                        try:
                            # Pod key'i namespace ve adına ayır
                            if '/' in old_pod_key:
                                namespace, pod_name = old_pod_key.split('/', 1)
                            else:
                                namespace = None
                                pod_name = old_pod_key
                                
                            with app.app_context():
                                # Mevcut alarmları bul
                                existing_alerts = Alert.query.filter(
                                    Alert.resource_type == "pod",
                                    Alert.resource_name == pod_name,
                                    Alert.is_resolved == 0
                                )
                                
                                if namespace:
                                    existing_alerts = existing_alerts.filter(Alert.resource_namespace == namespace)
                                
                                existing_alerts = existing_alerts.all()
                                
                                # Alarmları çözüldü olarak işaretle
                                for alert in existing_alerts:
                                    alert.resolve()
                                
                                # Kaydetmeyi tamamla
                                if existing_alerts:
                                    db.session.commit()
                                    logger.info(f"Marked {len(existing_alerts)} alerts as resolved for deleted pod {old_pod_key}")
                            
                            # Pod durumunu takip listesinden kaldır
                            pod_statuses.pop(old_pod_key, None)
                            logger.info(f"Removed tracking for deleted pod: {old_pod_key}")
                        except Exception as e:
                            logger.error(f"Error resolving alerts for deleted pod {old_pod_key}: {e}")
            
            logger.info(f"Monitored {len(pods)} pods")
        except Exception as e:
            logger.error(f"Error monitoring pods: {e}")
    
    def start_monitors(self):
        """Start monitoring threads"""
        logger.info("Starting Kubernetes monitor threads...")
        
        while True:
            try:
                self.monitor_nodes()
                self.monitor_pods()
                
                time.sleep(POLL_INTERVAL)
            except Exception as e:
                logger.error(f"Error in monitor loop: {e}")
                time.sleep(60)  # Wait before retrying

    def get_all_resources(self):
        """Get current state of all resources for the dashboard"""
        data = {
            "nodes": [],
            "pods": [],
            "alerts": []
        }
        
        # Get nodes
        try:
            try:
                nodes = self.core_v1.list_node().items
            except Exception as e:
                logger.warning(f"Failed to get nodes from Kubernetes API: {e}")
                if MOCK_DATA_AVAILABLE:
                    nodes = get_mock_nodes()
                    logger.info("Using mock node data for dashboard")
                else:
                    nodes = []
                    logger.error("No mock data available and Kubernetes API unreachable")
            
            for node in nodes:
                node_name = node.metadata.name
                node_status = "Ready"
                
                # Check node conditions
                for condition in node.status.conditions:
                    if condition.type == "Ready" and condition.status != "True":
                        node_status = "NotReady"
                
                data["nodes"].append({
                    "name": node_name,
                    "status": node_status,
                    "roles": [key.replace("node-role.kubernetes.io/", "") for key in node.metadata.labels.keys() if key.startswith("node-role.kubernetes.io/")],
                    "version": node.status.node_info.kubelet_version,
                    "cpu": node.status.capacity.get("cpu"),
                    "memory": node.status.capacity.get("memory")
                })
        except Exception as e:
            logger.error(f"Error getting nodes: {e}")
        
        # Get pods
        try:
            try:
                pods = self.core_v1.list_pod_for_all_namespaces().items
            except Exception as e:
                logger.warning(f"Failed to get pods from Kubernetes API: {e}")
                if MOCK_DATA_AVAILABLE:
                    pods = get_mock_pods()
                    logger.info("Using mock pod data for dashboard")
                else:
                    pods = []
                    logger.error("No mock data available and Kubernetes API unreachable")
            
            for pod in pods:
                pod_name = pod.metadata.name
                namespace = pod.metadata.namespace
                
                container_statuses = []
                if pod.status.container_statuses:
                    for container in pod.status.container_statuses:
                        state = "Unknown"
                        reason = ""
                        
                        if container.state.running:
                            state = "Running"
                        elif container.state.waiting:
                            state = "Waiting"
                            reason = container.state.waiting.reason
                        elif container.state.terminated:
                            state = "Terminated"
                            reason = container.state.terminated.reason
                        
                        container_statuses.append({
                            "name": container.name,
                            "ready": container.ready,
                            "restarts": container.restart_count,
                            "state": state,
                            "reason": reason
                        })
                
                data["pods"].append({
                    "name": pod_name,
                    "namespace": namespace,
                    "phase": pod.status.phase,
                    "containers": container_statuses,
                    "node": pod.spec.node_name,
                    "ip": pod.status.pod_ip
                })
        except Exception as e:
            logger.error(f"Error getting pods: {e}")
            
        # Add recent alerts from database instead of local variable
        # This ensures consistent data format with the main API
        try:
            with app.app_context():
                # is_resolved in database is an integer (0 for False, 1 for True)
                alerts = Alert.query.filter_by(is_resolved=0).order_by(Alert.created_at.desc()).limit(20).all()
                data["alerts"] = [
                    {
                        "id": alert.id,
                        "alert_key": alert.alert_key,
                        "resource_type": alert.resource_type,
                        "resource_name": alert.resource_name, 
                        "resource_namespace": alert.resource_namespace,
                        "status": alert.status,
                        "is_resolved": bool(alert.is_resolved),
                        "created_at": alert.created_at.isoformat() if alert.created_at else None,
                        "resolved_at": alert.resolved_at.isoformat() if alert.resolved_at else None,
                        "message": alert.message
                    } for alert in alerts
                ]
        except Exception as e:
            logger.error(f"Error getting database alerts: {e}")
            
        return data

# Create singleton instance
k8s_monitor = KubernetesMonitor()

def start_monitoring_thread():
    """Start a background thread for monitoring"""
    monitor_thread = threading.Thread(target=k8s_monitor.start_monitors, daemon=True)
    monitor_thread.start()
