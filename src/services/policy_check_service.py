"""Policy check service for analyzing advertising briefs."""

import json
import logging
import os
from datetime import UTC, datetime
from enum import Enum

import google.generativeai as genai
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# Sentinel value to distinguish "not provided" from "explicitly None"
_UNSET = object()


class PolicyStatus(str, Enum):
    """Policy compliance status options."""

    ALLOWED = "allowed"
    RESTRICTED = "restricted"
    BLOCKED = "blocked"


class PolicyCheckResult(BaseModel):
    """Result of policy compliance check."""

    status: PolicyStatus
    reason: str | None = None
    restrictions: list[str] | None = Field(default_factory=list)
    warnings: list[str] | None = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class PolicyCheckService:
    """Service for checking advertising briefs against policy compliance rules."""

    def __init__(self, gemini_api_key: str | None | object = _UNSET):
        """Initialize the policy check service.

        Args:
            gemini_api_key: Optional API key for Gemini. If not provided, uses GEMINI_API_KEY env var.
                           Pass explicit None to disable AI even if env var is set.
        """
        # If no argument provided, check environment
        if gemini_api_key is _UNSET:
            self.api_key = os.getenv("GEMINI_API_KEY")
        else:
            # Explicit argument provided (could be None or a key)
            self.api_key = gemini_api_key

        if not self.api_key:
            logger.warning("No Gemini API key provided. Policy checks will use basic rules only.")
            self.ai_enabled = False
        else:
            genai.configure(api_key=self.api_key)
            self.model = genai.GenerativeModel("gemini-flash-latest")
            self.ai_enabled = True

    async def check_brief_compliance(
        self,
        brief: str,
        promoted_offering: str | None = None,
        brand_manifest: dict | str | None = None,
        tenant_policies: dict | None = None,
    ) -> PolicyCheckResult:
        """Check if an advertising brief complies with policies.

        Args:
            brief: The advertising brief description
            promoted_offering: DEPRECATED: Use brand_manifest instead (still supported)
            brand_manifest: Brand manifest dict or URL string (preferred over promoted_offering)
            tenant_policies: Optional tenant-specific policy overrides

        Returns:
            PolicyCheckResult with compliance status and details
        """
        # Extract brand info from brand_manifest if provided
        brand_info = None
        if brand_manifest:
            if isinstance(brand_manifest, dict):
                # Extract name and description from manifest
                brand_name = brand_manifest.get("name", "")
                brand_description = brand_manifest.get("description", "")
                brand_info = f"{brand_name} - {brand_description}" if brand_description else brand_name
            elif isinstance(brand_manifest, str):
                # URL string - use as-is
                brand_info = f"Brand manifest URL: {brand_manifest}"

        # Fall back to promoted_offering if brand_manifest not provided
        if not brand_info and promoted_offering:
            brand_info = promoted_offering

        # Combine brief and brand info for analysis
        full_context = brief
        if brand_info:
            full_context = f"Brief: {brief}\n\nAdvertiser/Product: {brand_info}"

        # Always use AI analysis when available
        if self.ai_enabled:
            return await self._check_with_ai(full_context, tenant_policies)
        else:
            # Fallback if no AI is available - allow with warning
            return PolicyCheckResult(
                status=PolicyStatus.ALLOWED, warnings=["Policy check unavailable - AI service not configured"]
            )

    def _check_basic_rules(self, text: str) -> PolicyCheckResult:
        """Apply basic policy rules (deprecated - kept for compatibility).

        Args:
            text: Text to check

        Returns:
            PolicyCheckResult
        """
        # This method is deprecated since we always use AI analysis
        # Return allowed by default
        return PolicyCheckResult(status=PolicyStatus.ALLOWED, warnings=[])

    async def _check_with_ai(self, text: str, tenant_policies: dict | None = None) -> PolicyCheckResult:
        """Use AI to perform deep policy analysis.

        Args:
            text: Text to analyze
            tenant_policies: Optional tenant-specific policies

        Returns:
            PolicyCheckResult
        """
        system_prompt = """You are a policy compliance checker for advertising content.
Analyze the provided advertising brief and determine if it violates any advertising policies.

You must check for:
1. Targeting of vulnerable populations (children, elderly, disabled)
2. Discriminatory content based on protected characteristics
3. Illegal or heavily regulated products/services
4. Misleading or deceptive claims
5. Harmful content that could exploit users
6. Content that violates platform brand safety guidelines

Respond with a JSON object containing:
{
    "status": "allowed" | "restricted" | "blocked",
    "reason": "explanation if blocked",
    "restrictions": ["list of restrictions if status is restricted"],
    "warnings": ["list of policy warnings even if allowed"]
}

Be strict in your analysis. When in doubt, mark as restricted rather than allowed."""

        # Add tenant-specific policies if provided
        if tenant_policies:
            rules_text = []

            # Default prohibited categories and tactics are enforced for all
            default_categories = tenant_policies.get("default_prohibited_categories", [])
            default_tactics = tenant_policies.get("default_prohibited_tactics", [])

            # Combine default and custom policies
            all_prohibited_advertisers = tenant_policies.get("prohibited_advertisers", [])
            all_prohibited_categories = default_categories + tenant_policies.get("prohibited_categories", [])
            all_prohibited_tactics = default_tactics + tenant_policies.get("prohibited_tactics", [])

            if all_prohibited_advertisers:
                rules_text.append(f"Prohibited advertisers/domains: {', '.join(all_prohibited_advertisers)}")

            if all_prohibited_categories:
                rules_text.append(f"Prohibited content categories: {', '.join(all_prohibited_categories)}")

            if all_prohibited_tactics:
                rules_text.append(f"Prohibited advertising tactics: {', '.join(all_prohibited_tactics)}")

            if rules_text:
                system_prompt += "\n\nPolicy rules to enforce:\n" + "\n".join(rules_text)

        try:
            # Use async version of generate_content
            response = await self.model.generate_content_async(
                [
                    {"role": "user", "parts": [{"text": system_prompt}]},
                    {"role": "user", "parts": [{"text": f"Analyze this advertising brief:\n\n{text}"}]},
                ]
            )

            # Parse the JSON response
            result_text = response.text.strip()
            # Extract JSON from markdown if present
            if "```json" in result_text:
                result_text = result_text.split("```json")[1].split("```")[0].strip()
            elif "```" in result_text:
                result_text = result_text.split("```")[1].split("```")[0].strip()

            result_data = json.loads(result_text)

            return PolicyCheckResult(
                status=PolicyStatus(result_data.get("status", "allowed")),
                reason=result_data.get("reason"),
                restrictions=result_data.get("restrictions", []),
                warnings=result_data.get("warnings", []),
            )

        except Exception as e:
            logger.error(f"AI policy check failed: {str(e)}")
            # Fall back to allowed with warning
            return PolicyCheckResult(status=PolicyStatus.ALLOWED, warnings=[f"AI policy check unavailable: {str(e)}"])

    def check_product_eligibility(
        self, policy_result: PolicyCheckResult, product: dict, advertiser_category: str | None = None
    ) -> tuple[bool, str | None]:
        """Check if a product is eligible based on policy result and audience compatibility.

        Args:
            policy_result: Result from brief compliance check
            product: Product dictionary with audience characteristic fields
            advertiser_category: Optional advertiser category (e.g., 'alcohol', 'gambling')

        Returns:
            Tuple of (is_eligible, reason_if_not)
        """
        # Blocked briefs can't use any products
        if policy_result.status == PolicyStatus.BLOCKED:
            return False, policy_result.reason

        # Check age-based compatibility
        targeted_ages = product.get("targeted_ages")
        verified_minimum_age = product.get("verified_minimum_age")

        # Extract advertiser category from restrictions if not provided
        if not advertiser_category and policy_result.restrictions:
            # Try to infer category from restrictions
            restriction_text = " ".join(policy_result.restrictions).lower()
            if any(term in restriction_text for term in ["alcohol", "beer", "wine", "liquor"]):
                advertiser_category = "alcohol"
            elif any(term in restriction_text for term in ["gambling", "casino", "betting"]):
                advertiser_category = "gambling"
            elif any(term in restriction_text for term in ["tobacco", "cigarettes", "vaping"]):
                advertiser_category = "tobacco"
            elif any(term in restriction_text for term in ["cannabis", "marijuana", "cbd"]):
                advertiser_category = "cannabis"

        # Age-restricted categories require appropriate audience
        age_restricted_categories = ["alcohol", "gambling", "tobacco", "cannabis"]

        if advertiser_category in age_restricted_categories:
            # Cannot run on child-focused content
            if targeted_ages == "children":
                return False, f"{advertiser_category} advertising cannot run on child-focused content"

            # Check minimum age requirements
            if advertiser_category == "alcohol":
                required_age = 21
            else:  # gambling, tobacco, cannabis
                required_age = 18

            # Check if product has appropriate age verification
            if verified_minimum_age and verified_minimum_age >= required_age:
                # Product has age gating that meets requirements
                pass
            elif targeted_ages == "teens":
                # Teens content without age verification cannot have restricted ads
                return False, f"{advertiser_category} advertising requires {required_age}+ audience or age verification"
            elif not verified_minimum_age and targeted_ages != "adults":
                # No age verification and not explicitly adults-only
                return False, f"{advertiser_category} advertising requires age-gated content or adults-only audience"

        # Check for compatibility with restricted content
        if policy_result.status == PolicyStatus.RESTRICTED and targeted_ages == "children":
            # Children's content may not be suitable for restricted advertisers
            return False, "Children's content not compatible with restricted advertising"

        return True, None
