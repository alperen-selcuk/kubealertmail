# Kubernetes Monitoring Solution

![image](https://github.com/user-attachments/assets/e98081e6-d497-44a3-aa2d-7f87473d0f4e)



Real-time Kubernetes cluster monitoring and alert system - Track your cluster health instantly.

![image](https://github.com/user-attachments/assets/776f6b2a-1740-4858-a1bf-62d83e811dd8)


## About the Project

This project is a comprehensive monitoring solution that tracks Kubernetes clusters in real-time, monitors node and pod statuses, detects issues, and sends email alerts. Its primary purpose is to enable cluster administrators to quickly identify and resolve problems.

## Key Features

- **Real-Time Monitoring**: Continuously monitors node and pod statuses for instant visibility
- **Detailed Alerts**: Comprehensive alerts for pod failures, node issues, and container restarts
- **Email Notifications**: Automatic email notifications for critical issues
- **Data Persistence**: PostgreSQL database integration for alert history tracking
- **Intuitive Dashboard**: Easy-to-use visual graphs and filterable tables
- **Alert Management**: Capabilities to resolve, delete, and filter alerts

<img width="593" alt="image" src="https://github.com/user-attachments/assets/9cda3a53-5dca-4d00-ada8-e2c76e6d12f0" />


## How It Works

1. The application regularly checks pod and node statuses using the Kubernetes API
2. When issues are detected (CrashLoopBackOff, Pending, Failed, ImagePullBackOff, etc.), a detailed alert is created
3. Alerts are stored in the database and email notifications are sent
4. The web interface displays graphs and detailed error information for real-time monitoring
5. When issues are resolved, alerts are automatically closed

## Technical Specifications

- **Backend**: Python 3.10+, Flask, SQLAlchemy
- **Database**: PostgreSQL
- **Frontend**: JavaScript, Bootstrap, Chart.js
- **Kubernetes Integration**: Python Kubernetes Client
- **Configuration**: Kubernetes Secrets and ConfigMaps

## Installation

```bash
# Apply Kubernetes configuration files
kubectl apply -f kubernetes/

# Verify the application has started successfully
kubectl get pods -n monitoring
```

## Configuration

Configuring SMTP settings for email notifications:

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: monitoring-secrets
  namespace: monitoring
type: Opaque
data:
  SMTP_SERVER: your-base64-encoded-smtp-server
  SMTP_PORT: your-base64-encoded-smtp-port
  SMTP_USERNAME: your-base64-encoded-username
  SMTP_PASSWORD: your-base64-encoded-password
  EMAIL_FROM: your-base64-encoded-email
  EMAIL_TO: your-base64-encoded-recipients
```

## Contact

Contact: [alperenhasanselcuk@gmail.com](mailto:alperenhasanselcuk@gmail.com)

## License

This project is licensed under the MIT License. See the `LICENSE` file for more information.
