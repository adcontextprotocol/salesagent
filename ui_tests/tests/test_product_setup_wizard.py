"""Test the AI-assisted product setup wizard."""
import pytest
from playwright.async_api import Page, expect
import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent))
from utils.session_auth import SessionAuth


class TestProductSetupWizard:
    """Test suite for the product setup wizard."""
    
    @pytest.mark.asyncio
    async def test_wizard_navigation(self, page: Page, base_url: str):
        """Test basic wizard navigation flow."""
        # Check if authenticated first
        await page.goto(base_url)
        auth_status = await SessionAuth.check_current_auth(page)
        
        if not auth_status["logged_in"]:
            pytest.skip("Not authenticated - login manually first")
        
        # Navigate to products page
        await page.goto(f"{base_url}/tenant/default/products")
        
        # Should see the setup wizard button if no products exist
        wizard_button = page.locator('a:has-text("Start Product Setup Wizard")')
        
        if await wizard_button.count() > 0:
            # Click the wizard button
            await wizard_button.click()
            
            # Should be on step 1 - Markets
            await expect(page.locator('h3:has-text("Select Your Primary Markets")')).to_be_visible()
            
            # Check that US is pre-selected
            us_checkbox = page.locator('input[name="markets"][value="US"]')
            await expect(us_checkbox).to_be_checked()
            
            # Select additional market - Canada
            await page.locator('input[name="markets"][value="CA"]').check()
            
            # Test the country dropdown
            dropdown = page.locator('#country-select')
            await expect(dropdown).to_be_visible()
            
            # Click Next
            await page.locator('button:has-text("Next: Analyze Ad Server")').click()
            
            # Should be on step 2
            await expect(page.locator('h3:has-text("Analyzing Your Ad Server Configuration")')).to_be_visible()
            
            # Wait for analysis to complete
            await page.wait_for_selector('.analysis-item.complete', timeout=10000)
            
            # Click Next to see suggestions
            await page.locator('button:has-text("Next: Review Suggestions")').click()
            
            # Should be on step 3
            await expect(page.locator('h3:has-text("Suggested Products")')).to_be_visible()
            
            # Should see product suggestions
            await expect(page.locator('.product-suggestion').first).to_be_visible()
            
            print("✅ Wizard navigation test passed")
        else:
            print("ℹ️  Products already exist, skipping wizard test")
    
    @pytest.mark.asyncio
    async def test_country_dropdown(self, page: Page, base_url: str):
        """Test the country dropdown functionality."""
        # Check if authenticated first
        await page.goto(base_url)
        auth_status = await SessionAuth.check_current_auth(page)
        
        if not auth_status["logged_in"]:
            pytest.skip("Not authenticated - login manually first")
            
        await page.goto(f"{base_url}/tenant/default/products/setup-wizard")
        
        # Wait for page to load
        await page.wait_for_selector('#country-select')
        
        # Check dropdown is populated
        dropdown = page.locator('#country-select')
        await expect(dropdown).to_be_visible()
        
        # Open dropdown
        await dropdown.click()
        
        # Check some countries are present
        await dropdown.select_option('MX')  # Mexico
        
        # Click Add Market
        await page.locator('button:has-text("Add Market")').click()
        
        # Check Mexico was added
        mexico_checkbox = page.locator('input[name="markets"][value="MX"]')
        await expect(mexico_checkbox).to_be_visible()
        await expect(mexico_checkbox).to_be_checked()
        
        print("✅ Country dropdown test passed")
    
    @pytest.mark.asyncio
    async def test_pricing_controls(self, page: Page, base_url: str):
        """Test the pricing input controls."""
        # Check if authenticated first
        await page.goto(base_url)
        auth_status = await SessionAuth.check_current_auth(page)
        
        if not auth_status["logged_in"]:
            pytest.skip("Not authenticated - login manually first")
            
        await page.goto(f"{base_url}/tenant/default/products/setup-wizard")
        
        # Select US market
        await page.locator('input[name="markets"][value="US"]').check()
        
        # Navigate to suggestions
        await page.locator('button:has-text("Next: Analyze Ad Server")').click()
        await page.wait_for_selector('.analysis-item.complete', timeout=10000)
        await page.locator('button:has-text("Next: Review Suggestions")').click()
        
        # Wait for suggestions to load
        await page.wait_for_selector('.product-suggestion')
        
        # Test pricing controls on first product
        first_product = page.locator('.product-suggestion').first
        
        # Check for pricing type toggle
        fixed_radio = first_product.locator('input[value="fixed"]').first
        auction_radio = first_product.locator('input[value="auction"]').first
        
        await expect(fixed_radio.or_(auction_radio)).to_be_visible()
        
        # If auction is selected, switch to fixed
        if await auction_radio.is_checked():
            await fixed_radio.click()
            
            # Should see CPM input
            cpm_input = first_product.locator('input[placeholder="CPM"]').first
            await expect(cpm_input).to_be_visible()
            
            # Enter a CPM value
            await cpm_input.fill("5.50")
        
        # Switch to auction
        await auction_radio.click()
        
        # Should see min/max inputs
        min_input = first_product.locator('input[placeholder="Min"]').first
        max_input = first_product.locator('input[placeholder="Max"]').first
        
        await expect(min_input).to_be_visible()
        await expect(max_input).to_be_visible()
        
        # Enter price guidance
        await min_input.fill("2.00")
        await max_input.fill("10.00")
        
        print("✅ Pricing controls test passed")