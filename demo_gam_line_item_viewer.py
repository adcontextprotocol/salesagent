#!/usr/bin/env python3
"""
Demo server for GAM Line Item Viewer functionality.
Creates a mock Flask server with simulated GAM data for manual UI testing.
Not a unit test - run this to manually test the viewer UI with mock data.
"""

import json
from datetime import datetime, timedelta
from flask import Flask, jsonify, request, render_template
from werkzeug.serving import run_simple
import threading
import time

app = Flask(__name__, template_folder='templates', static_folder='static')
app.secret_key = 'test-secret-key'

# Mock GAM data
MOCK_LINE_ITEM_DATA = {
    "line_item": {
        "id": 5834526917,
        "orderId": 2857915125,
        "name": "Sports_Desktop_Display_Q1_2025",
        "externalId": "ADCP_001",
        "orderName": "Acme Corp - Q1 2025 Campaign",
        "startDateTime": {
            "date": {"year": 2025, "month": 1, "day": 1},
            "hour": 0,
            "minute": 0,
            "second": 0,
            "timeZoneId": "America/New_York"
        },
        "endDateTime": {
            "date": {"year": 2025, "month": 3, "day": 31},
            "hour": 23,
            "minute": 59,
            "second": 59,
            "timeZoneId": "America/New_York"
        },
        "autoExtensionDays": 0,
        "unlimitedEndDateTime": False,
        "creativeRotationType": "OPTIMIZED",
        "deliveryRateType": "EVENLY",
        "roadblockingType": "ONE_OR_MORE",
        "frequencyCaps": [
            {
                "maxImpressions": 10,
                "numTimeUnits": 1,
                "timeUnit": "DAY"
            }
        ],
        "lineItemType": "STANDARD",
        "priority": 8,
        "costPerUnit": {
            "currencyCode": "USD",
            "microAmount": 15000000
        },
        "valueCostPerUnit": {
            "currencyCode": "USD",
            "microAmount": 15000000
        },
        "costType": "CPM",
        "discountType": "PERCENTAGE",
        "discount": 0.0,
        "contractedUnitsBought": 1000000,
        "creativePlaceholders": [
            {
                "size": {"width": 728, "height": 90, "isAspectRatio": False},
                "expectedCreativeCount": 1,
                "creativeSizeType": "PIXEL",
                "targetingName": None,
                "isAmpOnly": False
            },
            {
                "size": {"width": 300, "height": 250, "isAspectRatio": False},
                "expectedCreativeCount": 1,
                "creativeSizeType": "PIXEL",
                "targetingName": None,
                "isAmpOnly": False
            }
        ],
        "environmentType": "BROWSER",
        "allowedFormats": ["HTML", "IMAGE"],
        "companionDeliveryOption": "OPTIONAL",
        "allowOverbook": False,
        "skipInventoryCheck": False,
        "skipCrossSellingRuleWarningChecks": False,
        "reserveAtCreation": False,
        "stats": {
            "impressionsDelivered": 456789,
            "clicksDelivered": 2341,
            "videoCompletionsDelivered": 0,
            "videoStartsDelivered": 0,
            "viewableImpressionsDelivered": 412345
        },
        "deliveryIndicator": {
            "expectedDeliveryPercentage": 45.7,
            "actualDeliveryPercentage": 45.6
        },
        "deliveryData": {
            "units": [{
                "unitType": "IMPRESSIONS",
                "unitAmount": 1000000
            }],
            "deliveryIndicator": {
                "expectedDeliveryPercentage": 45.7,
                "actualDeliveryPercentage": 45.6
            },
            "actualDeliveryAmount": 456789,
            "scheduledDeliveryAmount": 457000
        },
        "budget": {
            "currencyCode": "USD",
            "microAmount": 15000000000
        },
        "status": "DELIVERING",
        "reservationStatus": "RESERVED",
        "isArchived": False,
        "webPropertyCode": None,
        "appliedLabels": [],
        "effectiveAppliedLabels": [],
        "disableSameAdvertiserCompetitiveExclusion": False,
        "lastModifiedByApp": "Gam::UI",
        "notes": "Q1 2025 Sports campaign for desktop display",
        "competitiveConstraintScope": "POD",
        "lastModifiedDateTime": {
            "date": {"year": 2025, "month": 1, "day": 10},
            "hour": 14,
            "minute": 30,
            "second": 0,
            "timeZoneId": "America/New_York"
        },
        "creationDateTime": {
            "date": {"year": 2024, "month": 12, "day": 15},
            "hour": 10,
            "minute": 0,
            "second": 0,
            "timeZoneId": "America/New_York"
        },
        "isProgrammatic": False,
        "targeting": {
            "geoTargeting": {
                "targetedLocations": [
                    {
                        "id": 2840,
                        "type": "COUNTRY",
                        "canonicalParentId": None,
                        "displayName": "United States"
                    },
                    {
                        "id": 2124,
                        "type": "COUNTRY",
                        "canonicalParentId": None,
                        "displayName": "Canada"
                    }
                ],
                "excludedLocations": []
            },
            "inventoryTargeting": {
                "targetedAdUnits": [
                    {
                        "adUnitId": "21775744923",
                        "includeDescendants": True
                    }
                ],
                "excludedAdUnits": [],
                "targetedPlacementIds": []
            },
            "dayPartTargeting": {
                "timeZone": "PUBLISHER",
                "dayParts": [
                    {
                        "dayOfWeek": "MONDAY",
                        "startTime": {"hour": 6, "minute": 0},
                        "endTime": {"hour": 23, "minute": 59}
                    },
                    {
                        "dayOfWeek": "TUESDAY",
                        "startTime": {"hour": 6, "minute": 0},
                        "endTime": {"hour": 23, "minute": 59}
                    },
                    {
                        "dayOfWeek": "WEDNESDAY",
                        "startTime": {"hour": 6, "minute": 0},
                        "endTime": {"hour": 23, "minute": 59}
                    },
                    {
                        "dayOfWeek": "THURSDAY",
                        "startTime": {"hour": 6, "minute": 0},
                        "endTime": {"hour": 23, "minute": 59}
                    },
                    {
                        "dayOfWeek": "FRIDAY",
                        "startTime": {"hour": 6, "minute": 0},
                        "endTime": {"hour": 23, "minute": 59}
                    }
                ]
            },
            "technologyTargeting": {
                "deviceCategoryTargeting": {
                    "targetedDeviceCategories": [
                        {"id": 30000, "name": "Desktop"}
                    ],
                    "excludedDeviceCategories": []
                },
                "browserTargeting": {
                    "isTargeted": True,
                    "browsers": [
                        {"id": 500072, "name": "Chrome"},
                        {"id": 500082, "name": "Firefox"},
                        {"id": 500092, "name": "Safari"}
                    ]
                }
            },
            "customTargeting": {
                "logicalOperator": "OR",
                "children": [
                    {
                        "logicalOperator": "AND",
                        "children": [
                            {
                                "keyId": 12345,
                                "valueIds": [67890, 67891],
                                "operator": "IS"
                            }
                        ]
                    }
                ]
            },
            "contentTargeting": {
                "targetedContentIds": [],
                "excludedContentIds": [],
                "targetedVideoCategoryIds": []
            },
            "videoPositionTargeting": None,
            "mobileApplicationTargeting": None,
            "buyerUserListTargeting": None,
            "requestPlatformTargeting": None
        }
    },
    "order": {
        "id": 2857915125,
        "name": "Acme Corp - Q1 2025 Campaign",
        "startDateTime": {
            "date": {"year": 2025, "month": 1, "day": 1},
            "hour": 0,
            "minute": 0,
            "second": 0,
            "timeZoneId": "America/New_York"
        },
        "endDateTime": {
            "date": {"year": 2025, "month": 3, "day": 31},
            "hour": 23,
            "minute": 59,
            "second": 59,
            "timeZoneId": "America/New_York"
        },
        "unlimitedEndDateTime": False,
        "status": "APPROVED",
        "isArchived": False,
        "notes": "Q1 2025 campaign for Acme Corp",
        "externalOrderId": 54321,
        "poNumber": "PO-2025-Q1-001",
        "currencyCode": "USD",
        "advertiserId": 4563534,
        "advertiserContactIds": [],
        "agencyId": None,
        "agencyContactIds": [],
        "creatorId": 245563,
        "traffickerId": 245563,
        "secondaryTraffickerIds": [],
        "salespersonId": 245564,
        "secondarySalespersonIds": [],
        "totalImpressionsDelivered": 456789,
        "totalClicksDelivered": 2341,
        "totalViewableImpressionsDelivered": 412345,
        "totalBudget": {
            "currencyCode": "USD",
            "microAmount": 15000000000
        },
        "appliedLabels": [],
        "effectiveAppliedLabels": [],
        "isProgrammatic": False
    },
    "creatives": [
        {
            "id": 138251188213,
            "name": "AcmeCorp_Sports_728x90",
            "advertiserId": 4563534,
            "width": 728,
            "height": 90,
            "isAspectRatio": False,
            "Creative.Type": "ImageCreative",
            "destinationUrl": "https://www.acmecorp.example/sports",
            "destinationUrlType": "CLICK_TO_WEB",
            "size": {"width": 728, "height": 90, "isAspectRatio": False},
            "previewUrl": "https://pubads.g.doubleclick.net/gampad/ad?iu=/21775744923/sports&sz=728x90",
            "lastModifiedDateTime": {
                "date": {"year": 2025, "month": 1, "day": 5},
                "hour": 10,
                "minute": 30,
                "second": 0,
                "timeZoneId": "America/New_York"
            }
        },
        {
            "id": 138251188214,
            "name": "AcmeCorp_Sports_300x250",
            "advertiserId": 4563534,
            "width": 300,
            "height": 250,
            "isAspectRatio": False,
            "Creative.Type": "ImageCreative",
            "destinationUrl": "https://www.acmecorp.example/sports",
            "destinationUrlType": "CLICK_TO_WEB",
            "size": {"width": 300, "height": 250, "isAspectRatio": False},
            "previewUrl": "https://pubads.g.doubleclick.net/gampad/ad?iu=/21775744923/sports&sz=300x250",
            "lastModifiedDateTime": {
                "date": {"year": 2025, "month": 1, "day": 5},
                "hour": 10,
                "minute": 30,
                "second": 0,
                "timeZoneId": "America/New_York"
            }
        }
    ],
    "creative_associations": [
        {
            "lineItemId": 5834526917,
            "creativeId": 138251188213,
            "Creative.Type": "LineItemCreativeAssociation",
            "status": "ACTIVE",
            "stats": {
                "impressionsDelivered": 228394,
                "clicksDelivered": 1170
            },
            "lastModifiedDateTime": {
                "date": {"year": 2025, "month": 1, "day": 5},
                "hour": 10,
                "minute": 30,
                "second": 0,
                "timeZoneId": "America/New_York"
            }
        },
        {
            "lineItemId": 5834526917,
            "creativeId": 138251188214,
            "Creative.Type": "LineItemCreativeAssociation",
            "status": "ACTIVE",
            "stats": {
                "impressionsDelivered": 228395,
                "clicksDelivered": 1171
            },
            "lastModifiedDateTime": {
                "date": {"year": 2025, "month": 1, "day": 5},
                "hour": 10,
                "minute": 30,
                "second": 0,
                "timeZoneId": "America/New_York"
            }
        }
    ],
    "media_product_json": {
        "product_id": "gam_line_item_5834526917",
        "name": "Sports_Desktop_Display_Q1_2025",
        "description": "GAM Line Item: Sports_Desktop_Display_Q1_2025",
        "formats": [
            {"format": "display_728x90", "min_spend": 100.0},
            {"format": "display_300x250", "min_spend": 100.0}
        ],
        "delivery_type": "guaranteed",
        "is_fixed_price": True,
        "cpm": 15.0,
        "targeting_overlay": {
            "geo_country_any_of": ["US", "CA"],
            "device_any_of": ["desktop"],
            "browser_any_of": ["chrome", "firefox", "safari"],
            "dayparting": {
                "timezone": "America/New_York",
                "schedules": [
                    {"days": ["monday", "tuesday", "wednesday", "thursday", "friday"],
                     "start_hour": 6,
                     "end_hour": 23}
                ]
            },
            "frequency_cap": {
                "suppress_minutes": 1440,
                "scope": "media_buy"
            }
        },
        "implementation_config": {
            "gam": {
                "line_item_id": 5834526917,
                "order_id": 2857915125,
                "line_item_type": "STANDARD",
                "delivery_settings": {
                    "delivery_rate_type": "EVENLY",
                    "frequency_caps": [
                        {"max_impressions": 10, "time_unit": "DAY", "num_time_units": 1}
                    ]
                }
            }
        }
    }
}

@app.route('/api/tenant/<tenant_id>/gam/line-item/<line_item_id>')
def mock_get_gam_line_item(tenant_id, line_item_id):
    """Mock endpoint that returns test GAM line item data."""
    # Simulate different line items with variations
    if line_item_id == "5834526917":
        return jsonify(MOCK_LINE_ITEM_DATA)
    elif line_item_id == "404":
        return jsonify({"error": "Line item not found"}), 404
    else:
        # Generate a simple mock response for any other ID
        simple_data = MOCK_LINE_ITEM_DATA.copy()
        simple_data["line_item"]["id"] = int(line_item_id)
        simple_data["line_item"]["name"] = f"Test_Line_Item_{line_item_id}"
        return jsonify(simple_data)

@app.route('/tenant/<tenant_id>/gam/line-item/<line_item_id>')
def view_gam_line_item(tenant_id, line_item_id):
    """Render the GAM line item viewer template."""
    tenant = {
        'tenant_id': tenant_id,
        'name': 'Test Publisher'
    }
    return render_template('gam_line_item_viewer.html',
                          tenant=tenant,
                          tenant_id=tenant_id,
                          line_item_id=line_item_id,
                          user_email='test@example.com')

@app.route('/')
def index():
    """Simple index page with links to test the viewer."""
    return '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>GAM Line Item Viewer Test</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 40px; }
            h1 { color: #333; }
            .link-list { margin-top: 20px; }
            .link-list a { display: block; margin: 10px 0; color: #007bff; }
        </style>
    </head>
    <body>
        <h1>GAM Line Item Viewer Test</h1>
        <p>Click on a link below to test the GAM Line Item Viewer:</p>
        <div class="link-list">
            <a href="/tenant/test_publisher/gam/line-item/5834526917">View Line Item 5834526917 (Full Mock Data)</a>
            <a href="/tenant/test_publisher/gam/line-item/1234567890">View Line Item 1234567890 (Simple Mock)</a>
            <a href="/tenant/test_publisher/gam/line-item/404">View Line Item 404 (Error Test)</a>
        </div>
    </body>
    </html>
    '''

if __name__ == '__main__':
    print("\n" + "="*60)
    print("GAM Line Item Viewer Test Server")
    print("="*60)
    print("\nStarting test server on http://localhost:8002")
    print("\nAvailable test endpoints:")
    print("  - http://localhost:8002/ (Test index page)")
    print("  - http://localhost:8002/tenant/test_publisher/gam/line-item/5834526917")
    print("  - http://localhost:8002/tenant/test_publisher/gam/line-item/1234567890")
    print("  - http://localhost:8002/tenant/test_publisher/gam/line-item/404")
    print("\nPress Ctrl+C to stop the server\n")
    
    app.run(host='0.0.0.0', port=8002, debug=True)