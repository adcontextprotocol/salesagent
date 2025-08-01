#!/usr/bin/env python3
"""
Conductor Port Management System

Manages a pool of predefined ports for Conductor workspaces to avoid
having to constantly update Google OAuth redirect URIs.
"""

import json
import os
import sys
import fcntl
from datetime import datetime
from pathlib import Path


class ConductorPortManager:
    def __init__(self, config_file="conductor_ports.json"):
        self.config_file = Path(config_file).absolute()
        self.lock_file = self.config_file.with_suffix('.lock')
        
    def _load_config(self):
        """Load port configuration with file locking."""
        with open(self.config_file, 'r') as f:
            return json.load(f)
    
    def _save_config(self, config):
        """Save port configuration with file locking."""
        with open(self.config_file, 'w') as f:
            json.dump(config, f, indent=2)
    
    def _with_lock(self, func):
        """Execute function with exclusive file lock."""
        lock_fd = os.open(str(self.lock_file), os.O_CREAT | os.O_WRONLY, 0o600)
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX)
            return func()
        finally:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            os.close(lock_fd)
    
    def reserve_ports(self, workspace_name):
        """Reserve a port set for a workspace."""
        def _reserve():
            config = self._load_config()
            
            # Check if workspace already has ports reserved
            if workspace_name in config['reserved_ports']:
                return config['reserved_ports'][workspace_name]
            
            # Find first available port set
            for i, port_set in enumerate(config['available_port_sets']):
                # Check if this port set is already reserved
                is_reserved = False
                for reserved in config['reserved_ports'].values():
                    if reserved['ports'] == port_set:
                        is_reserved = True
                        break
                
                if not is_reserved:
                    # Reserve this port set
                    reservation = {
                        'ports': port_set,
                        'reserved_at': datetime.now().isoformat(),
                        'index': i
                    }
                    config['reserved_ports'][workspace_name] = reservation
                    self._save_config(config)
                    return reservation
            
            raise RuntimeError("No available port sets! All ports are reserved.")
        
        return self._with_lock(_reserve)
    
    def release_ports(self, workspace_name):
        """Release ports reserved by a workspace."""
        def _release():
            config = self._load_config()
            
            if workspace_name in config['reserved_ports']:
                del config['reserved_ports'][workspace_name]
                self._save_config(config)
                return True
            return False
        
        return self._with_lock(_release)
    
    def get_reserved_ports(self, workspace_name):
        """Get ports reserved by a workspace."""
        config = self._load_config()
        if workspace_name in config['reserved_ports']:
            return config['reserved_ports'][workspace_name]['ports']
        return None
    
    def list_reservations(self):
        """List all current port reservations."""
        config = self._load_config()
        return config['reserved_ports']
    
    def get_oauth_urls(self):
        """Generate list of OAuth redirect URLs for all port sets."""
        config = self._load_config()
        urls = []
        for port_set in config['available_port_sets']:
            urls.append(f"http://localhost:{port_set['admin']}/callback")
        return urls


def main():
    if len(sys.argv) < 2:
        print("Usage: python manage_conductor_ports.py <command> [args]")
        print("Commands:")
        print("  reserve <workspace_name>  - Reserve ports for a workspace")
        print("  release <workspace_name>  - Release ports for a workspace")
        print("  list                      - List all reservations")
        print("  oauth-urls                - List all OAuth redirect URLs")
        sys.exit(1)
    
    manager = ConductorPortManager()
    command = sys.argv[1]
    
    if command == "reserve":
        if len(sys.argv) < 3:
            print("Error: workspace name required")
            sys.exit(1)
        workspace = sys.argv[2]
        try:
            reservation = manager.reserve_ports(workspace)
            ports = reservation['ports']
            print(f"Reserved ports for {workspace}:")
            print(f"  PostgreSQL: {ports['postgres']}")
            print(f"  MCP Server: {ports['mcp']}")
            print(f"  Admin UI: {ports['admin']}")
        except RuntimeError as e:
            print(f"Error: {e}")
            sys.exit(1)
    
    elif command == "release":
        if len(sys.argv) < 3:
            print("Error: workspace name required")
            sys.exit(1)
        workspace = sys.argv[2]
        if manager.release_ports(workspace):
            print(f"Released ports for {workspace}")
        else:
            print(f"No ports reserved for {workspace}")
    
    elif command == "list":
        reservations = manager.list_reservations()
        if not reservations:
            print("No port reservations")
        else:
            print("Current port reservations:")
            for workspace, info in reservations.items():
                ports = info['ports']
                print(f"\n{workspace}:")
                print(f"  PostgreSQL: {ports['postgres']}")
                print(f"  MCP Server: {ports['mcp']}")
                print(f"  Admin UI: {ports['admin']}")
                print(f"  Reserved at: {info['reserved_at']}")
    
    elif command == "oauth-urls":
        urls = manager.get_oauth_urls()
        print("Add these redirect URLs to your Google OAuth configuration:")
        for url in urls:
            print(f"  {url}")
    
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)


if __name__ == "__main__":
    main()