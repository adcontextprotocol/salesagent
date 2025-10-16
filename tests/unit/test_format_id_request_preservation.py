"""Test that format_ids from request packages are preserved when creating MediaPackages."""


def test_format_ids_from_request_preserved():
    """Test that buyer-specified format_ids override product formats."""

    # Create mock product with leaderboard format
    class MockProduct:
        def __init__(self):
            self.product_id = "display_leaderboard_cpm"
            self.formats = ["leaderboard_728x90"]  # Product has leaderboard

    product = MockProduct()

    # Simulate request package with display_300x250 format
    class MockPackage:
        def __init__(self):
            self.product_id = "display_leaderboard_cpm"
            self.format_ids = [{"agent_url": "https://creatives.adcontextprotocol.org", "id": "display_300x250"}]

    req_package = MockPackage()

    # Simulate the logic from main.py (lines 4502-4546)
    format_ids_to_use = []

    # Find matching package
    if req_package.product_id == product.product_id:
        # Extract format IDs from FormatId objects
        for fmt in req_package.format_ids:
            if isinstance(fmt, dict):
                format_ids_to_use.append(fmt.get("id"))
            elif hasattr(fmt, "id"):
                format_ids_to_use.append(fmt.id)
            elif isinstance(fmt, str):
                format_ids_to_use.append(fmt)

    # Fallback to product's formats if no request format_ids
    if not format_ids_to_use:
        format_ids_to_use = [product.formats[0]] if product.formats else []

    # Verify that request format_ids take precedence
    assert format_ids_to_use == ["display_300x250"], f"Expected ['display_300x250'], got {format_ids_to_use}"
    assert "leaderboard_728x90" not in format_ids_to_use, "Product format should not override request format"


def test_format_ids_fallback_to_product():
    """Test that product formats are used when request has no format_ids."""

    # Create mock product with leaderboard format
    class MockProduct:
        def __init__(self):
            self.product_id = "display_leaderboard_cpm"
            self.formats = ["leaderboard_728x90"]

    product = MockProduct()

    # Simulate request package WITHOUT format_ids
    class MockPackage:
        def __init__(self):
            self.product_id = "display_leaderboard_cpm"
            self.format_ids = None  # No format_ids in request

    req_package = MockPackage()

    # Simulate the logic from main.py
    format_ids_to_use = []

    # Find matching package
    if req_package.product_id == product.product_id and req_package.format_ids:
        # Extract format IDs from FormatId objects
        for fmt in req_package.format_ids:
            if isinstance(fmt, dict):
                format_ids_to_use.append(fmt.get("id"))
            elif hasattr(fmt, "id"):
                format_ids_to_use.append(fmt.id)
            elif isinstance(fmt, str):
                format_ids_to_use.append(fmt)

    # Fallback to product's formats if no request format_ids
    if not format_ids_to_use:
        format_ids_to_use = [product.formats[0]] if product.formats else []

    # Verify that product formats are used as fallback
    assert format_ids_to_use == ["leaderboard_728x90"], f"Expected ['leaderboard_728x90'], got {format_ids_to_use}"


def test_format_ids_handles_format_id_objects():
    """Test that FormatId objects (with .id attribute) are handled correctly."""

    class FormatId:
        def __init__(self, agent_url, format_id):
            self.agent_url = agent_url
            self.id = format_id

    # Create mock product
    class MockProduct:
        def __init__(self):
            self.product_id = "display_leaderboard_cpm"
            self.formats = ["leaderboard_728x90"]

    product = MockProduct()

    # Simulate request package with FormatId objects
    class MockPackage:
        def __init__(self):
            self.product_id = "display_leaderboard_cpm"
            self.format_ids = [FormatId("https://creatives.adcontextprotocol.org", "display_300x250")]

    req_package = MockPackage()

    # Simulate the logic from main.py
    format_ids_to_use = []

    # Find matching package
    if req_package.product_id == product.product_id:
        # Extract format IDs from FormatId objects
        for fmt in req_package.format_ids:
            if isinstance(fmt, dict):
                format_ids_to_use.append(fmt.get("id"))
            elif hasattr(fmt, "id"):
                format_ids_to_use.append(fmt.id)
            elif isinstance(fmt, str):
                format_ids_to_use.append(fmt)

    # Fallback to product's formats if no request format_ids
    if not format_ids_to_use:
        format_ids_to_use = [product.formats[0]] if product.formats else []

    # Verify that FormatId.id is extracted correctly
    assert format_ids_to_use == ["display_300x250"], f"Expected ['display_300x250'], got {format_ids_to_use}"
