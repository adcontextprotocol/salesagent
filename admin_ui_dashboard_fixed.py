# Fixed dashboard route with proper database queries
from flask import render_template
from datetime import datetime, timezone
import os

def tenant_dashboard_fixed(tenant_id, conn):
    """Fixed version of tenant dashboard with proper database queries."""
    
    # Get tenant basic info
    cursor = conn.execute("""
        SELECT tenant_id, name, subdomain, is_active, ad_server
        FROM tenants WHERE tenant_id = %s
    """, (tenant_id,))
    row = cursor.fetchone()
    if not row:
        return None
    
    tenant = {
        'tenant_id': row[0],
        'name': row[1],
        'subdomain': row[2],
        'is_active': row[3],
        'ad_server': row[4]
    }
    
    # Get metrics
    metrics = {}
    
    # Total revenue (30 days) - using the actual budget column
    cursor = conn.execute("""
        SELECT COALESCE(SUM(budget), 0) as total_revenue
        FROM media_buys 
        WHERE tenant_id = %s 
        AND status IN ('active', 'completed')
        AND created_at >= CURRENT_TIMESTAMP - INTERVAL '30 days'
    """, (tenant_id,))
    metrics['total_revenue'] = cursor.fetchone()[0] or 0
    
    # Revenue change vs previous period
    cursor = conn.execute("""
        SELECT COALESCE(SUM(budget), 0) as prev_revenue
        FROM media_buys 
        WHERE tenant_id = %s 
        AND status IN ('active', 'completed')
        AND created_at >= CURRENT_TIMESTAMP - INTERVAL '60 days'
        AND created_at < CURRENT_TIMESTAMP - INTERVAL '30 days'
    """, (tenant_id,))
    prev_revenue = cursor.fetchone()[0] or 0
    if prev_revenue > 0:
        metrics['revenue_change'] = ((metrics['total_revenue'] - prev_revenue) / prev_revenue) * 100
    else:
        metrics['revenue_change'] = 0
    
    # Active media buys
    cursor = conn.execute("""
        SELECT COUNT(*) FROM media_buys 
        WHERE tenant_id = %s AND status = 'active'
    """, (tenant_id,))
    metrics['active_buys'] = cursor.fetchone()[0]
    
    # Pending media buys
    cursor = conn.execute("""
        SELECT COUNT(*) FROM media_buys 
        WHERE tenant_id = %s AND status = 'pending'
    """, (tenant_id,))
    metrics['pending_buys'] = cursor.fetchone()[0]
    
    # Open tasks (using human_tasks table)
    cursor = conn.execute("""
        SELECT COUNT(*) FROM human_tasks 
        WHERE tenant_id = %s AND status IN ('pending', 'in_progress')
    """, (tenant_id,))
    metrics['open_tasks'] = cursor.fetchone()[0]
    
    # Overdue tasks (tasks older than 3 days)
    cursor = conn.execute("""
        SELECT COUNT(*) FROM human_tasks 
        WHERE tenant_id = %s 
        AND status IN ('pending', 'in_progress')
        AND created_at < CURRENT_TIMESTAMP - INTERVAL '3 days'
    """, (tenant_id,))
    metrics['overdue_tasks'] = cursor.fetchone()[0]
    
    # Active advertisers (principals with activity in last 30 days)
    cursor = conn.execute("""
        SELECT COUNT(DISTINCT principal_id) 
        FROM media_buys 
        WHERE tenant_id = %s 
        AND created_at >= CURRENT_TIMESTAMP - INTERVAL '30 days'
    """, (tenant_id,))
    metrics['active_advertisers'] = cursor.fetchone()[0]
    
    # Total advertisers
    cursor = conn.execute("""
        SELECT COUNT(*) FROM principals WHERE tenant_id = %s
    """, (tenant_id,))
    metrics['total_advertisers'] = cursor.fetchone()[0]
    
    # Get recent media buys with actual schema
    cursor = conn.execute("""
        SELECT 
            mb.media_buy_id,
            mb.principal_id,
            mb.advertiser_name,
            mb.status,
            mb.budget,
            0 as spend,  -- TODO: Calculate actual spend
            mb.created_at
        FROM media_buys mb
        WHERE mb.tenant_id = %s
        ORDER BY mb.created_at DESC
        LIMIT 10
    """, (tenant_id,))
    
    recent_media_buys = []
    for row in cursor.fetchall():
        # Calculate relative time
        created_at = row[6] if row[6] else datetime.now(timezone.utc)
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
        now = datetime.now(timezone.utc)
        delta = now - created_at
        
        if delta.days > 0:
            relative_time = f"{delta.days}d ago"
        elif delta.seconds > 3600:
            relative_time = f"{delta.seconds // 3600}h ago"
        else:
            relative_time = f"{delta.seconds // 60}m ago"
        
        recent_media_buys.append({
            'media_buy_id': row[0],
            'principal_id': row[1],
            'advertiser_name': row[2] or 'Unknown',
            'status': row[3],
            'budget': row[4] or 0,
            'spend': row[5],
            'created_at_relative': relative_time
        })
    
    # Get product count
    cursor = conn.execute("""
        SELECT COUNT(*) FROM products WHERE tenant_id = %s
    """, (tenant_id,))
    product_count = cursor.fetchone()[0]
    
    # Get pending tasks with proper query
    cursor = conn.execute("""
        SELECT task_type, 
               CASE 
                   WHEN details::text != '' AND details IS NOT NULL
                   THEN (details::json->>'description')::text
                   ELSE task_type
               END as description
        FROM human_tasks 
        WHERE tenant_id = %s AND status = 'pending'
        ORDER BY created_at DESC
        LIMIT 5
    """, (tenant_id,))
    
    pending_tasks = []
    for row in cursor.fetchall():
        pending_tasks.append({
            'type': row[0],
            'description': row[1] or row[0]
        })
    
    # Chart data for revenue by advertiser (last 7 days)
    cursor = conn.execute("""
        SELECT 
            mb.advertiser_name,
            SUM(mb.budget) as revenue
        FROM media_buys mb
        WHERE mb.tenant_id = %s
        AND mb.created_at >= CURRENT_TIMESTAMP - INTERVAL '7 days'
        AND mb.status IN ('active', 'completed')
        GROUP BY mb.advertiser_name
        ORDER BY revenue DESC
        LIMIT 10
    """, (tenant_id,))
    
    chart_labels = []
    chart_data = []
    for row in cursor.fetchall():
        chart_labels.append(row[0] or 'Unknown')
        chart_data.append(float(row[1]) if row[1] else 0)
    
    # Get admin port from environment
    admin_port = os.environ.get('ADMIN_UI_PORT', '8001')
    
    return {
        'tenant': tenant,
        'metrics': metrics,
        'recent_media_buys': recent_media_buys,
        'product_count': product_count,
        'pending_tasks': pending_tasks,
        'chart_labels': chart_labels,
        'chart_data': chart_data,
        'admin_port': admin_port
    }