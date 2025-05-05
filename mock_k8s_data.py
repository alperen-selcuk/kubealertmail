import logging
import uuid
from datetime import datetime
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

# Mock Kubernetes sınıfları
@dataclass
class V1ObjectMeta:
    name: str
    namespace: str = "default"
    labels: Dict[str, str] = field(default_factory=dict)
    uid: str = field(default_factory=lambda: str(uuid.uuid4()))

@dataclass
class V1NodeSystemInfo:
    kubelet_version: str
    operating_system: str = "linux"
    architecture: str = "amd64"
    container_runtime_version: str = "containerd://1.4.6"
    boot_id: str = field(default_factory=lambda: str(uuid.uuid4()))

@dataclass
class V1NodeCondition:
    type: str
    status: str
    reason: str = "KubeletReady"
    message: str = "kubelet is posting ready status"
    last_transition_time: str = field(default_factory=lambda: datetime.now().isoformat())

@dataclass
class V1NodeStatus:
    conditions: List[V1NodeCondition] = field(default_factory=list)
    node_info: V1NodeSystemInfo = None
    capacity: Dict[str, str] = field(default_factory=dict)
    
    def __post_init__(self):
        if self.node_info is None:
            self.node_info = V1NodeSystemInfo(kubelet_version="v1.21.0")

@dataclass
class V1NodeSpec:
    taints: List[Any] = field(default_factory=list)

@dataclass
class V1Node:
    metadata: V1ObjectMeta
    status: V1NodeStatus
    spec: V1NodeSpec = field(default_factory=V1NodeSpec)

@dataclass
class V1ContainerStateRunning:
    started_at: str = field(default_factory=lambda: datetime.now().isoformat())

@dataclass
class V1ContainerStateWaiting:
    reason: str
    message: str

@dataclass
class V1ContainerStateTerminated:
    reason: str
    exit_code: int
    message: str
    started_at: str = field(default_factory=lambda: datetime.now().isoformat())
    finished_at: str = field(default_factory=lambda: datetime.now().isoformat())

@dataclass
class V1ContainerState:
    running: Optional[V1ContainerStateRunning] = None
    waiting: Optional[V1ContainerStateWaiting] = None
    terminated: Optional[V1ContainerStateTerminated] = None

@dataclass
class V1ContainerStatus:
    name: str
    ready: bool
    restart_count: int
    state: V1ContainerState
    image: str = "k8s.gcr.io/pause:3.5"
    image_id: str = "sha256:1234567890abcdef"
    container_id: str = field(default_factory=lambda: f"containerd://{uuid.uuid4()}")

@dataclass
class V1Container:
    name: str
    image: str = "k8s.gcr.io/pause:3.5"

@dataclass
class V1PodSpec:
    containers: List[V1Container] = field(default_factory=list)
    node_name: Optional[str] = None

@dataclass
class V1PodStatus:
    phase: str
    pod_ip: Optional[str] = None
    container_statuses: List[V1ContainerStatus] = field(default_factory=list)

@dataclass
class V1Pod:
    metadata: V1ObjectMeta
    status: V1PodStatus
    spec: V1PodSpec

logger = logging.getLogger(__name__)

def get_mock_nodes():
    """Generate mock Kubernetes node data for demonstration"""
    mock_nodes = []
    roles = ["master", "worker", "worker"]
    statuses = ["True", "True", "False"]
    
    for i in range(3):
        labels = {}
        if roles[i] == "master":
            labels["node-role.kubernetes.io/master"] = ""
        else:
            labels["node-role.kubernetes.io/worker"] = ""
            
        meta = V1ObjectMeta(
            name=f"node-{i+1}",
            labels=labels
        )
        
        conditions = [
            V1NodeCondition(
                type="Ready",
                status=statuses[i],
                reason="KubeletReady" if statuses[i] == "True" else "NodeNotReady",
                message="kubelet is posting ready status" if statuses[i] == "True" else "Node is not ready",
                last_transition_time=datetime.now().isoformat()
            )
        ]
        
        status = V1NodeStatus(
            conditions=conditions,
            node_info=V1NodeSystemInfo(
                kubelet_version=f"v1.21.{i}",
                operating_system="linux",
                architecture="amd64",
                container_runtime_version="containerd://1.4.6"
            ),
            capacity={
                "cpu": str(2 + i*2),
                "memory": f"{4 + i*4}Gi"
            }
        )
        
        node = V1Node(
            metadata=meta,
            status=status,
            spec=V1NodeSpec()
        )
        
        mock_nodes.append(node)
    
    logger.info(f"Created {len(mock_nodes)} mock nodes for demonstration")
    return mock_nodes

def get_mock_pods():
    """Generate mock Kubernetes pod data for demonstration"""
    mock_pods = []
    namespaces = ["default", "kube-system", "monitoring", "app", "database"]
    phases = ["Running", "Running", "Pending", "Running", "Failed"]
    nodes = ["node-1", "node-2", "node-1", None, "node-3"]
    
    for ns_idx, namespace in enumerate(namespaces):
        for i in range(3):  # 3 pods per namespace
            pod_name = f"{namespace}-pod-{i+1}"
            meta = V1ObjectMeta(
                name=pod_name,
                namespace=namespace
            )
            
            # Determine pod phase
            phase_idx = (ns_idx + i) % len(phases)
            phase = phases[phase_idx]
            
            # Determine node assignment
            node_idx = (ns_idx + i) % len(nodes)
            node_name = nodes[node_idx]
            
            # Create container statuses
            container_statuses = []
            for j in range(1 + i % 2):  # 1 or 2 containers per pod
                container_name = f"container-{j+1}"
                
                # Create container state
                state = None
                if phase == "Running":
                    state = V1ContainerState(
                        running=V1ContainerStateRunning(
                            started_at=datetime.now().isoformat()
                        )
                    )
                elif phase == "Pending":
                    # Pending durumundaki bazı pod'ları ImagePullBackOff durumuna getir
                    if (ns_idx + i) % 3 == 0:  # Her 3 pod'dan biri ImagePullBackOff olsun
                        state = V1ContainerState(
                            waiting=V1ContainerStateWaiting(
                                reason="ImagePullBackOff",
                                message="Back-off pulling image example.com/my-app:latest - Error: ErrImagePull"
                            )
                        )
                    else:
                        state = V1ContainerState(
                            waiting=V1ContainerStateWaiting(
                                reason="ContainerCreating",
                                message="Container is being created"
                            )
                        )
                elif phase == "Failed":
                    if j == 0:  # First container in failed pods will be in CrashLoopBackOff
                        state = V1ContainerState(
                            waiting=V1ContainerStateWaiting(
                                reason="CrashLoopBackOff",
                                message="Back-off restarting failed container"
                            )
                        )
                    else:
                        state = V1ContainerState(
                            terminated=V1ContainerStateTerminated(
                                reason="Error",
                                exit_code=1,
                                message="Container exited with error"
                            )
                        )
                
                # Create restart count (more for failed pods)
                restart_count = 0
                if phase == "Failed":
                    restart_count = 5 + i
                
                # Create container status
                container_status = V1ContainerStatus(
                    name=container_name,
                    ready=phase == "Running",
                    restart_count=restart_count,
                    state=state
                )
                
                container_statuses.append(container_status)
            
            # Create pod status
            status = V1PodStatus(
                phase=phase,
                pod_ip=f"10.0.{ns_idx}.{i+1}" if phase == "Running" else None,
                container_statuses=container_statuses
            )
            
            # Create pod spec
            spec = V1PodSpec(
                node_name=node_name,
                containers=[V1Container(name=cs.name) for cs in container_statuses]
            )
            
            # Create pod
            pod = V1Pod(
                metadata=meta,
                status=status,
                spec=spec
            )
            
            mock_pods.append(pod)
    
    logger.info(f"Created {len(mock_pods)} mock pods for demonstration")
    return mock_pods