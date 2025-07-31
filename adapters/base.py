from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from datetime import datetime
from rich.console import Console
from schemas import *
from audit_logger import get_audit_logger

class CreativeEngineAdapter(ABC):
    """Abstract base class for creative engine adapters."""
    @abstractmethod
    def process_assets(self, media_buy_id: str, assets: List[Dict[str, Any]]) -> List[AssetStatus]:
        pass

class AdServerAdapter(ABC):
    """Abstract base class for ad server adapters."""

    def __init__(
        self, 
        config: Dict[str, Any], 
        principal: Principal,
        dry_run: bool = False,
        creative_engine: Optional[CreativeEngineAdapter] = None,
        tenant_id: Optional[str] = None
    ):
        self.config = config
        self.principal = principal
        self.principal_id = principal.principal_id  # For backward compatibility
        self.dry_run = dry_run
        self.creative_engine = creative_engine
        self.tenant_id = tenant_id
        self.console = Console()
        
        # Set adapter_principal_id after initialization when adapter_name is available
        if hasattr(self.__class__, 'adapter_name'):
            self.adapter_principal_id = principal.get_adapter_id(self.__class__.adapter_name)
        else:
            self.adapter_principal_id = None
            
        # Initialize audit logger with adapter name and tenant_id
        adapter_name = getattr(self.__class__, 'adapter_name', self.__class__.__name__)
        self.audit_logger = get_audit_logger(adapter_name, tenant_id)
        
        # Manual approval mode - requires human approval for all operations
        self.manual_approval_required = config.get('manual_approval_required', False)
        self.manual_approval_operations = set(config.get('manual_approval_operations', [
            'create_media_buy', 'update_media_buy', 'add_creative_assets'
        ]))
        
    def log(self, message: str, dry_run_prefix: bool = True):
        """Log a message, with optional dry-run prefix."""
        if self.dry_run and dry_run_prefix:
            self.console.print(f"[dim](dry-run)[/dim] {message}")
        else:
            self.console.print(message)

    @abstractmethod
    def create_media_buy(
        self,
        request: CreateMediaBuyRequest,
        packages: List[MediaPackage],
        start_time: datetime,
        end_time: datetime
    ) -> CreateMediaBuyResponse:
        """Creates a new media buy on the ad server from selected packages."""
        pass

    @abstractmethod
    def add_creative_assets(
        self,
        media_buy_id: str,
        assets: List[Dict[str, Any]],
        today: datetime
    ) -> List[AssetStatus]:
        """Adds creative assets to an existing media buy."""
        pass

    @abstractmethod
    def check_media_buy_status(
        self,
        media_buy_id: str,
        today: datetime
    ) -> CheckMediaBuyStatusResponse:
        """Checks the status of a media buy on the ad server."""
        pass

    @abstractmethod
    def get_media_buy_delivery(
        self,
        media_buy_id: str,
        date_range: ReportingPeriod,
        today: datetime
    ) -> AdapterGetMediaBuyDeliveryResponse:
        """Gets delivery data for a media buy."""
        pass

    @abstractmethod
    def update_media_buy_performance_index(
        self,
        media_buy_id: str,
        package_performance: List[PackagePerformance]
    ) -> bool:
        """Updates the performance index for packages in a media buy."""
        pass

    @abstractmethod
    def update_media_buy(
        self,
        media_buy_id: str,
        action: str,
        package_id: Optional[str],
        budget: Optional[int],
        today: datetime
    ) -> UpdateMediaBuyResponse:
        """Updates a media buy with a specific action."""
        pass
    
    def get_config_ui_endpoint(self) -> Optional[str]:
        """
        Returns the endpoint path for this adapter's configuration UI.
        If None, the adapter doesn't provide a custom UI.
        
        Example: "/adapters/gam/config" 
        """
        return None
    
    def register_ui_routes(self, app):
        """
        Register Flask routes for this adapter's configuration UI.
        Called during app initialization if the adapter provides UI.
        
        Example:
        @app.route('/adapters/gam/config/<tenant_id>/<product_id>')
        def gam_product_config(tenant_id, product_id):
            return render_template('gam_config.html', ...)
        """
        pass
    
    def validate_product_config(self, config: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        """
        Validate product-specific configuration for this adapter.
        Returns (is_valid, error_message)
        """
        return True, None