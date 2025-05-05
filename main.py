import os
import logging
from flask import Flask, render_template, jsonify, request
from k8s_monitor import k8s_monitor, start_monitoring_thread
from models import db, Alert

# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Initialize Flask app
# Note: The Flask app in models.py is now the main app
from models import app

# Start the Kubernetes monitoring in a background thread
start_monitoring_thread()

@app.route('/')
def index():
    """Render the main dashboard page"""
    return render_template('index.html')

@app.route('/dashboard')
def dashboard():
    """Render the dashboard template"""
    return render_template('dashboard.html')

@app.route('/api/resources')
def api_resources():
    """API endpoint to get current resources status"""
    try:
        data = k8s_monitor.get_all_resources()
        return jsonify(data)
    except Exception as e:
        logger.error(f"Error getting resources: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/alerts')
def api_alerts():
    """API endpoint to get alerts from the database"""
    try:
        # Get status filter parameter - Default is 'active'
        status_filter = request.args.get('status', 'active')
        
        # Create query
        query = Alert.query
        
        # Apply status filter
        if status_filter == 'active':
            query = query.filter(Alert.is_resolved == 0)
        elif status_filter == 'resolved':
            query = query.filter(Alert.is_resolved == 1)
        
        # Sort with most recent first
        query = query.order_by(Alert.created_at.desc())
        
        # Execute query and get results
        alerts = query.all()
        
        # Format alerts for JSON response
        alerts_data = []
        for alert in alerts:
            # If 'status' value is 'None' or similar, replace with 'Unknown'
            status_value = alert.status if alert.status else 'Unknown'
            
            alerts_data.append({
                'id': alert.id,
                'alert_key': alert.alert_key,
                'resource_type': alert.resource_type,
                'resource_name': alert.resource_name,
                'resource_namespace': alert.resource_namespace,
                'status': status_value,
                'message': alert.message,
                'created_at': alert.created_at.isoformat() if alert.created_at else None,
                'resolved_at': alert.resolved_at.isoformat() if alert.resolved_at else None,
                'is_resolved': bool(alert.is_resolved)
            })
        
        return jsonify({'alerts': alerts_data})
    except Exception as e:
        logger.error(f"Error getting alerts: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/alerts/<int:alert_id>', methods=['DELETE'])
def delete_alert(alert_id):
    """Delete an alert from the database"""
    try:
        # Find the alert
        alert = Alert.query.get(alert_id)
        
        if not alert:
            return jsonify({"error": "Alert not found"}), 404
        
        # Delete the alert
        db.session.delete(alert)
        db.session.commit()
        
        logger.info(f"Deleted alert with ID {alert_id}")
        return jsonify({"success": True, "message": f"Alert {alert_id} successfully deleted"})
    except Exception as e:
        logger.error(f"Error deleting alert: {e}")
        return jsonify({"error": str(e)}), 500
    
@app.route('/api/alerts/<int:alert_id>/resolve', methods=['PUT'])
def resolve_alert(alert_id):
    """Mark an alert as resolved"""
    try:
        # Find the alert
        alert = Alert.query.get(alert_id)
        
        if not alert:
            return jsonify({"error": "Alert not found"}), 404
        
        # Mark as resolved
        alert.resolve()
        db.session.commit()
        
        logger.info(f"Resolved alert with ID {alert_id}")
        return jsonify({"success": True, "message": f"Alert {alert_id} marked as resolved"})
    except Exception as e:
        logger.error(f"Error resolving alert: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/healthz')
def health_check():
    """Kubernetes health check endpoint"""
    return jsonify({"status": "ok"})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
