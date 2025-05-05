import os
from sqlalchemy import Column, Integer, String, DateTime, Text
from sqlalchemy.sql import func
from flask_sqlalchemy import SQLAlchemy
from flask import Flask

# create the app
app = Flask(__name__)
# setup a secret key, required by sessions
app.secret_key = os.environ.get("FLASK_SECRET_KEY") or "a secret key"
# configure the database, relative to the app instance folder
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_recycle": 300,
    "pool_pre_ping": True,
}

# Debug the env vars
print(f"Database URL: {os.environ.get('DATABASE_URL')}")
print(f"Other PG Variables: PGHOST={os.environ.get('PGHOST')}, PGPORT={os.environ.get('PGPORT')}")

db = SQLAlchemy(app)

class Alert(db.Model):
    __tablename__ = 'alerts'
    
    id = Column(Integer, primary_key=True)
    alert_key = Column(String(255), nullable=False, index=True)
    resource_type = Column(String(50), nullable=False)
    resource_name = Column(String(255), nullable=False)
    resource_namespace = Column(String(255), nullable=True)
    status = Column(String(50), nullable=False)
    message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=func.now(), nullable=False)
    resolved_at = Column(DateTime, nullable=True)
    is_resolved = Column(Integer, default=0, nullable=False)
    
    def __repr__(self):
        return f'<Alert {self.alert_key}>'
    
    @staticmethod
    def parse_alert_key(alert_key):
        """Parse an alert key into its components"""
        parts = alert_key.split(':')
        
        resource_type = parts[0]
        resource_name = parts[1]
        status = parts[2] if len(parts) > 2 else 'Unknown'
        extra = parts[3] if len(parts) > 3 else None
        
        return resource_type, resource_name, status, extra
    
    @classmethod
    def from_alert_key(cls, alert_key, message=None, namespace=None):
        """Create a new Alert object from an alert key"""
        resource_type, resource_name, status, extra = cls.parse_alert_key(alert_key)
        
        return cls(
            alert_key=alert_key,
            resource_type=resource_type,
            resource_name=resource_name,
            resource_namespace=namespace,
            status=status,
            message=message
        )
    
    def resolve(self):
        """Mark the alert as resolved"""
        self.is_resolved = 1
        self.resolved_at = func.now()

# Initialize the database
with app.app_context():
    db.create_all()