import unittest
import json
import os
from main import _get_proposal_logic, Proposal, init_db

class TestAdcpServer(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        """Set up the database once for all tests."""
        # Use an in-memory database for testing to not interfere with the main db
        init_db()

    def test_proposal_validation(self):
        """
        Tests that get_proposal returns a valid Proposal object,
        even with non-deterministic AI responses. This is the most crucial test.
        """
        with open('brief.json', 'r') as f:
            brief_data = json.load(f)
        
        brief = brief_data.get("brief")
        provided_signals = brief_data.get("provided_signals")

        # Call the tool's underlying function directly for testing
        try:
            proposal = _get_proposal_logic(brief=brief, provided_signals=provided_signals)
            
            # The primary assertion: does the output conform to our Pydantic model?
            self.assertIsInstance(proposal, Proposal)
            
            # We can also do some basic sanity checks that don't depend on the AI's exact choices
            self.assertGreaterEqual(proposal.total_budget, 0)
            self.assertIsInstance(proposal.media_packages, list)
            
            print("\n--- Test Proposal Validation Passed ---")
            print(f"Generated Proposal ID: {proposal.proposal_id}")
            print(f"Total Packages: {len(proposal.media_packages)}")
            print("------------------------------------")

        except Exception as e:
            self.fail(f"get_proposal raised an exception: {e}")

    def test_database_initialization(self):
        """
        Tests the deterministic database initialization.
        """
        db_file = "adcp.db"
        # Ensure the file exists after init
        self.assertTrue(os.path.exists(db_file))
        print(f"\n--- Test Database Initialization Passed ---")

if __name__ == '__main__':
    unittest.main()
