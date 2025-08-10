"""Context manager for maintaining conversation state across messages."""

import json
import uuid
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from sqlalchemy.orm import Session
from models import Context, ContextMessage
from db_config import get_db_connection
import logging

logger = logging.getLogger(__name__)

class ContextManager:
    """Manages conversation context persistence for A2A and MCP protocols."""
    
    DEFAULT_CONTEXT_TTL_HOURS = 24
    MAX_MESSAGES_PER_CONTEXT = 100
    
    def __init__(self):
        """Initialize context manager."""
        pass
    
    def get_or_create_context(
        self,
        context_id: Optional[str],
        tenant_id: str,
        principal_id: str,
        protocol: str = "a2a"
    ) -> str:
        """
        Get existing context or create a new one.
        
        Args:
            context_id: Optional existing context ID
            tenant_id: Tenant identifier
            principal_id: Principal/user identifier
            protocol: Protocol type ('a2a' or 'mcp')
            
        Returns:
            Context ID (existing or newly created)
        """
        conn = get_db_connection()
        
        try:
            # If context_id provided, try to retrieve it
            if context_id:
                cursor = conn.execute("""
                    SELECT context_id, is_active, expires_at 
                    FROM contexts 
                    WHERE context_id = ? AND tenant_id = ? AND principal_id = ? AND is_active = ?
                """, (context_id, tenant_id, principal_id, True))
                
                row = cursor.fetchone()
                if row:
                    # Update last_accessed_at
                    conn.execute("""
                        UPDATE contexts 
                        SET last_accessed_at = CURRENT_TIMESTAMP 
                        WHERE context_id = ?
                    """, (context_id,))
                    conn.connection.commit() if hasattr(conn, 'connection') else conn.commit()
                    return context_id
            
            # Create new context - use provided context_id if available, otherwise generate one
            new_context_id = context_id if context_id else f"ctx_{uuid.uuid4().hex[:12]}"
            expires_at = datetime.utcnow() + timedelta(hours=self.DEFAULT_CONTEXT_TTL_HOURS)
            
            conn.execute("""
                INSERT INTO contexts (
                    context_id, tenant_id, principal_id, protocol,
                    state, metadata, expires_at, is_active
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                new_context_id, tenant_id, principal_id, protocol,
                json.dumps({}), json.dumps({}), expires_at, True
            ))
            
            conn.connection.commit() if hasattr(conn, 'connection') else conn.commit()
            logger.info(f"Created new context: {new_context_id} for {principal_id}")
            return new_context_id
            
        except Exception as e:
            logger.error(f"Error managing context: {e}")
            conn.connection.rollback() if hasattr(conn, 'connection') else conn.rollback()
            # Raise the error so callers know there's an issue
            raise RuntimeError(f"Failed to manage context: {e}") from e
        finally:
            conn.close()
    
    def save_message(
        self,
        context_id: str,
        message_type: str,
        method: Optional[str],
        request_data: Optional[Dict],
        response_data: Optional[Dict]
    ):
        """
        Save a message to the context history.
        
        Args:
            context_id: Context identifier
            message_type: 'request' or 'response'
            method: The method/tool being called
            request_data: Request payload
            response_data: Response payload
        """
        conn = get_db_connection()
        
        try:
            # Get next sequence number
            cursor = conn.execute("""
                SELECT COALESCE(MAX(sequence_num), 0) + 1 
                FROM context_messages 
                WHERE context_id = ?
            """, (context_id,))
            
            next_seq = cursor.fetchone()[0]
            
            # Limit message history to MAX_MESSAGES_PER_CONTEXT
            if next_seq > self.MAX_MESSAGES_PER_CONTEXT:
                # Archive or truncate old messages
                conn.execute("""
                    DELETE FROM context_messages 
                    WHERE context_id = ? AND sequence_num < ?
                """, (context_id, next_seq - self.MAX_MESSAGES_PER_CONTEXT))
            
            # Insert new message
            message_id = f"msg_{uuid.uuid4().hex[:12]}"
            
            conn.execute("""
                INSERT INTO context_messages (
                    message_id, context_id, sequence_num, message_type,
                    method, request_data, response_data
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                message_id, context_id, next_seq, message_type,
                method,
                json.dumps(request_data) if request_data else None,
                json.dumps(response_data) if response_data else None
            ))
            
            conn.connection.commit() if hasattr(conn, 'connection') else conn.commit()
            logger.debug(f"Saved {message_type} message to context {context_id}")
            
        except Exception as e:
            logger.error(f"Error saving message to context {context_id}: {e}")
            conn.connection.rollback() if hasattr(conn, 'connection') else conn.rollback()
            # Re-raise to inform caller
            raise RuntimeError(f"Failed to save message: {e}") from e
        finally:
            conn.close()
    
    def get_context_state(self, context_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve the current state for a context.
        
        Args:
            context_id: Context identifier
            
        Returns:
            Context state and metadata dictionary
        """
        conn = get_db_connection()
        
        try:
            cursor = conn.execute("""
                SELECT state, metadata 
                FROM contexts 
                WHERE context_id = ? AND is_active = ?
            """, (context_id, True))
            
            row = cursor.fetchone()
            if row:
                return {
                    'state': json.loads(row[0]) if row[0] else {},
                    'metadata': json.loads(row[1]) if row[1] else {}
                }
            return None
            
        except Exception as e:
            logger.error(f"Error retrieving context state: {e}")
            return None
        finally:
            conn.close()
    
    def update_context_state(
        self,
        context_id: str,
        state: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """
        Update the state for a context.
        
        Args:
            context_id: Context identifier
            state: New state data
            metadata: New metadata
        """
        conn = get_db_connection()
        
        try:
            updates = []
            params = []
            
            if state is not None:
                updates.append("state = ?")
                params.append(json.dumps(state))
            
            if metadata is not None:
                updates.append("metadata = ?")
                params.append(json.dumps(metadata))
            
            if updates:
                # Use static SQL to avoid injection - only two possible combinations
                if state is not None and metadata is not None:
                    conn.execute("""
                        UPDATE contexts 
                        SET state = ?, metadata = ?, updated_at = CURRENT_TIMESTAMP
                        WHERE context_id = ?
                    """, (json.dumps(state), json.dumps(metadata), context_id))
                elif state is not None:
                    conn.execute("""
                        UPDATE contexts 
                        SET state = ?, updated_at = CURRENT_TIMESTAMP
                        WHERE context_id = ?
                    """, (json.dumps(state), context_id))
                elif metadata is not None:
                    conn.execute("""
                        UPDATE contexts 
                        SET metadata = ?, updated_at = CURRENT_TIMESTAMP
                        WHERE context_id = ?
                    """, (json.dumps(metadata), context_id))
                
                conn.connection.commit() if hasattr(conn, 'connection') else conn.commit()
                logger.debug(f"Updated context state for {context_id}")
                
        except Exception as e:
            logger.error(f"Error updating context state: {e}")
            conn.connection.rollback() if hasattr(conn, 'connection') else conn.rollback()
        finally:
            conn.close()
    
    def get_conversation_history(
        self,
        context_id: str,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Retrieve conversation history for a context.
        
        Args:
            context_id: Context identifier
            limit: Maximum number of messages to retrieve
            
        Returns:
            List of message dictionaries
        """
        conn = get_db_connection()
        
        try:
            cursor = conn.execute("""
                SELECT sequence_num, message_type, method, 
                       request_data, response_data, created_at
                FROM context_messages 
                WHERE context_id = ?
                ORDER BY sequence_num DESC
                LIMIT ?
            """, (context_id, limit))
            
            messages = []
            for row in cursor.fetchall():
                messages.append({
                    'sequence_num': row[0],
                    'message_type': row[1],
                    'method': row[2],
                    'request_data': json.loads(row[3]) if row[3] else None,
                    'response_data': json.loads(row[4]) if row[4] else None,
                    'created_at': row[5].isoformat() if row[5] else None
                })
            
            return messages
            
        except Exception as e:
            logger.error(f"Error retrieving conversation history: {e}")
            return []
        finally:
            conn.close()
    
    def invalidate_context(self, context_id: str) -> bool:
        """
        Mark a context as inactive.
        
        Args:
            context_id: Context identifier
            
        Returns:
            True if context was invalidated, False otherwise
        """
        conn = get_db_connection()
        
        try:
            cursor = conn.execute("""
                UPDATE contexts 
                SET is_active = ?, updated_at = CURRENT_TIMESTAMP
                WHERE context_id = ? AND is_active = ?
            """, (False, context_id, True))
            
            affected = cursor.rowcount
            conn.connection.commit() if hasattr(conn, 'connection') else conn.commit()
            
            # Also delete associated messages
            conn.execute("""
                DELETE FROM context_messages 
                WHERE context_id = ?
            """, (context_id,))
            
            deleted = cursor.rowcount
            conn.connection.commit() if hasattr(conn, 'connection') else conn.commit()
            
            logger.info(f"Invalidated context {context_id}, deleted {deleted} messages")
            return affected > 0
            
        except Exception as e:
            logger.error(f"Error invalidating context: {e}")
            conn.connection.rollback() if hasattr(conn, 'connection') else conn.rollback()
            return False
        finally:
            conn.close()
    
    def cleanup_expired_contexts(self):
        """Clean up expired contexts based on TTL."""
        conn = get_db_connection()
        
        try:
            # Mark expired contexts as inactive
            cursor = conn.execute("""
                UPDATE contexts 
                SET is_active = ?
                WHERE expires_at < CURRENT_TIMESTAMP AND is_active = ?
            """, (False, True))
            
            expired_count = cursor.rowcount
            
            if expired_count > 0:
                # Delete messages for expired contexts
                conn.execute("""
                    DELETE FROM context_messages 
                    WHERE context_id IN (
                        SELECT context_id FROM contexts 
                        WHERE is_active = ?
                    )
                """, (False,))
                
                conn.connection.commit() if hasattr(conn, 'connection') else conn.commit()
                logger.info(f"Cleaned up {expired_count} expired contexts")
                
        except Exception as e:
            logger.error(f"Error cleaning up expired contexts: {e}")
            conn.connection.rollback() if hasattr(conn, 'connection') else conn.rollback()
        finally:
            conn.close()