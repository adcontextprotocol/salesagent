"""
Audit logging module for AdCP Sales Agent platform.

Implements security-compliant logging with:
- Timestamps
- Principal context
- Operation tracking
- Success/failure status
- Database-based audit trail with optional file backup
"""

import logging
import os
from datetime import datetime
from typing import Optional, Dict, Any
from pathlib import Path
import json
from db_config import get_db_connection

# Create logs directory if it doesn't exist (for backup)
LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)

# Configure logging format
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# Set up file handler for backup
audit_handler = logging.FileHandler(LOG_DIR / "audit.log")
audit_handler.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))

# Set up error handler  
error_handler = logging.FileHandler(LOG_DIR / "error.log")
error_handler.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))
error_handler.setLevel(logging.ERROR)

# Create audit logger
audit_logger = logging.getLogger("adcp.audit")
audit_logger.setLevel(logging.INFO)
audit_logger.addHandler(audit_handler)
audit_logger.addHandler(error_handler)

# Also log to console for debugging
console_handler = logging.StreamHandler()
console_handler.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))
audit_logger.addHandler(console_handler)


class AuditLogger:
    """Provides security-compliant audit logging for AdCP operations."""
    
    def __init__(self, adapter_name: str, tenant_id: Optional[str] = None):
        self.adapter_name = adapter_name
        self.tenant_id = tenant_id
        
    def log_operation(
        self,
        operation: str,
        principal_name: str,
        principal_id: str,
        adapter_id: str,
        success: bool = True,
        details: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
        tenant_id: Optional[str] = None
    ):
        """Log an adapter operation with full audit context.
        
        Args:
            operation: The operation being performed (e.g., "create_media_buy")
            principal_name: Human-readable principal name
            principal_id: Internal principal ID
            adapter_id: Platform-specific advertiser ID
            success: Whether the operation succeeded
            details: Additional operation details
            error: Error message if operation failed
            tenant_id: Override tenant ID (uses instance tenant_id if not provided)
        """
        # Use provided tenant_id or fall back to instance tenant_id
        tenant_id = tenant_id or self.tenant_id
        
        # Build log message in security documentation format
        message = f"{self.adapter_name}.{operation} for principal '{principal_name}' ({self.adapter_name} advertiser ID: {adapter_id})"
        
        if success:
            audit_logger.info(message)
            if details:
                for key, value in details.items():
                    audit_logger.info(f"  {key}: {value}")
        else:
            audit_logger.error(f"{message} - FAILED")
            if error:
                audit_logger.error(f"  Error: {error}")
                
        # Write to database
        try:
            conn = get_db_connection()
            conn.execute("""
                INSERT INTO audit_logs (
                    tenant_id, timestamp, operation, principal_name, 
                    principal_id, adapter_id, success, error_message, details
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                tenant_id,
                datetime.utcnow().isoformat(),
                f"{self.adapter_name}.{operation}",
                principal_name,
                principal_id,
                adapter_id,
                success,
                error if not success else None,
                json.dumps(details) if details else None
            ))
            conn.connection.commit()
            conn.close()
        except Exception as e:
            audit_logger.error(f"Failed to write audit log to database: {e}")
            # Continue with file logging as fallback
                
        # Also write structured JSON log for machine processing (backup)
        self._write_structured_log(
            operation=operation,
            principal_name=principal_name,
            principal_id=principal_id,
            adapter_id=adapter_id,
            success=success,
            details=details,
            error=error,
            tenant_id=tenant_id
        )
    
    def log_security_violation(
        self,
        operation: str,
        principal_id: str,
        resource_id: str,
        reason: str,
        tenant_id: Optional[str] = None
    ):
        """Log a security violation attempt."""
        # Use provided tenant_id or fall back to instance tenant_id
        tenant_id = tenant_id or self.tenant_id
        
        message = (
            f"SECURITY VIOLATION: {self.adapter_name}.{operation} "
            f"Principal '{principal_id}' attempted to access resource '{resource_id}' - {reason}"
        )
        audit_logger.error(message)
        
        # Write to database
        try:
            conn = get_db_connection()
            conn.execute("""
                INSERT INTO audit_logs (
                    tenant_id, timestamp, operation, principal_name, 
                    principal_id, adapter_id, success, error_message, details
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                tenant_id,
                datetime.utcnow().isoformat(),
                f"SECURITY_VIOLATION:{self.adapter_name}.{operation}",
                None,  # principal_name not available
                principal_id,
                None,  # adapter_id not applicable
                False,  # Security violations are failures
                f"Attempted to access resource '{resource_id}' - {reason}",
                json.dumps({"resource_id": resource_id, "reason": reason})
            ))
            conn.connection.commit()
            conn.close()
        except Exception as e:
            audit_logger.error(f"Failed to write security violation to database: {e}")
        
        # Write to security log (backup)
        self._write_security_log(
            operation=operation,
            principal_id=principal_id,
            resource_id=resource_id,
            reason=reason,
            tenant_id=tenant_id
        )
    
    def log_success(self, message: str):
        """Log a success message with checkmark."""
        audit_logger.info(f"✓ {message}")
    
    def log_warning(self, message: str):
        """Log a warning message."""
        audit_logger.warning(f"⚠️  {message}")
        
    def log_info(self, message: str):
        """Log an informational message."""
        audit_logger.info(message)
        
    def _write_structured_log(self, **kwargs):
        """Write structured JSON log for machine processing (backup)."""
        log_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "adapter": self.adapter_name,
            **kwargs
        }
        
        try:
            with open(LOG_DIR / "structured.jsonl", "a") as f:
                f.write(json.dumps(log_entry) + "\n")
        except Exception as e:
            audit_logger.error(f"Failed to write structured log: {e}")
    
    def _write_security_log(self, **kwargs):
        """Write security-specific log entry (backup)."""
        log_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "adapter": self.adapter_name,
            "type": "security_violation",
            **kwargs
        }
        
        try:
            with open(LOG_DIR / "security.jsonl", "a") as f:
                f.write(json.dumps(log_entry) + "\n")
        except Exception as e:
            audit_logger.error(f"Failed to write security log: {e}")


# Convenience function for getting logger
def get_audit_logger(adapter_name: str, tenant_id: Optional[str] = None) -> AuditLogger:
    """Get an audit logger instance for the specified adapter."""
    return AuditLogger(adapter_name, tenant_id)