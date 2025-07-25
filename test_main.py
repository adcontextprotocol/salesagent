import unittest
import json
import os
from datetime import datetime, timedelta

from main import get_packages, create_media_buy, _check_creative_compatibility
from schemas import *
from database import init_db

class TestAdcpServerV2(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        """Set up the database once for all tests."""
        if os.path.exists("adcp.db"):
            os.remove("adcp.db")
        init_db()

    def test_get_packages(self):
        """
        Tests that get_packages returns a valid GetPackagesResponse object
        with correctly structured packages and creative compatibility.
        """
        request = GetPackagesRequest(
            budget=100000,
            currency="USD",
            start_time=datetime.now(),
            end_time=datetime.now() + timedelta(days=30),
            creatives=[
                CreativeAsset(id="cr-1", media_type="display", mime="image/png", w=300, h=250),
                CreativeAsset(id="cr-2", media_type="video", mime="video/mp4", w=1920, h=1080, dur=30),
                CreativeAsset(id="cr-3", media_type="display", mime="image/jpeg", w=728, h=90) # Incompatible
            ],
            targeting={"provided_signals": []}
        )

        try:
            response = get_packages.fn(request=request)
            
            self.assertIsInstance(response, GetPackagesResponse)
            self.assertEqual(len(response.packages), 2)

            # Test guaranteed package
            guaranteed_pkg = next(p for p in response.packages if p.delivery_type == 'guaranteed')
            self.assertEqual(guaranteed_pkg.type, 'catalog')
            self.assertIsNotNone(guaranteed_pkg.cpm)
            self.assertTrue(guaranteed_pkg.creative_compatibility['cr-1'].compatible)
            self.assertFalse(guaranteed_pkg.creative_compatibility['cr-2'].compatible)

            # Test non-guaranteed package
            non_guaranteed_pkg = next(p for p in response.packages if p.delivery_type == 'non_guaranteed')
            self.assertEqual(non_guaranteed_pkg.type, 'catalog')
            self.assertIsNotNone(non_guaranteed_pkg.pricing)
            self.assertEqual(non_guaranteed_pkg.pricing.suggested_cpm, 7.5)
            self.assertFalse(non_guaranteed_pkg.creative_compatibility['cr-1'].compatible)
            self.assertTrue(non_guaranteed_pkg.creative_compatibility['cr-2'].compatible)

        except Exception as e:
            self.fail(f"get_packages raised an exception: {e}")

if __name__ == '__main__':
    unittest.main()