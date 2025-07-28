"""
Audit logging module for AdCP:Buy platform.

Implements security-compliant logging with:
- Timestamps
- Principal context
- Operation tracking
- Success/failure status
- File-based audit trail
"""

import logging
import os
from datetime import datetime
from typing import Optional, Dict, Any
from pathlib import Path
import json

# Create logs directory if it doesn't exist
LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)

# Configure logging format
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# Set up file handler
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
    
    def __init__(self, adapter_name: str):
        self.adapter_name = adapter_name
        
    def log_operation(
        self,
        operation: str,
        principal_name: str,
        principal_id: str,
        adapter_id: str,
        success: bool = True,
        details: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None
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
        """
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
                
        # Also write structured JSON log for machine processing
        self._write_structured_log(
            operation=operation,
            principal_name=principal_name,
            principal_id=principal_id,
            adapter_id=adapter_id,
            success=success,
            details=details,
            error=error
        )
    
    def log_security_violation(
        self,
        operation: str,
        principal_id: str,
        resource_id: str,
        reason: str
    ):
        """Log a security violation attempt."""
        message = (
            f"SECURITY VIOLATION: {self.adapter_name}.{operation} "
            f"Principal '{principal_id}' attempted to access resource '{resource_id}' - {reason}"
        )
        audit_logger.error(message)
        
        # Write to security log
        self._write_security_log(
            operation=operation,
            principal_id=principal_id,
            resource_id=resource_id,
            reason=reason
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
        """Write structured JSON log for machine processing."""
        log_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "adapter": self.adapter_name,
            **kwargs
        }
        
        with open(LOG_DIR / "structured.jsonl", "a") as f:
            f.write(json.dumps(log_entry) + "\n")
    
    def _write_security_log(self, **kwargs):
        """Write security-specific log entry."""
        log_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "adapter": self.adapter_name,
            "type": "security_violation",
            **kwargs
        }
        
        with open(LOG_DIR / "security.jsonl", "a") as f:
            f.write(json.dumps(log_entry) + "\n")


# Convenience function for getting logger
def get_audit_logger(adapter_name: str) -> AuditLogger:
    """Get an audit logger instance for the specified adapter."""
    return AuditLogger(adapter_name)