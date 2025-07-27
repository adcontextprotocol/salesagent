# AdCP:Buy Dry-Run Mode Demonstration

This demonstrates the adapter-based dry-run logging functionality.

## Command-Line Usage

```bash
# Run simulation with mock adapter in dry-run mode
python run_simulation.py --dry-run --adapter mock

# Run simulation with Google Ad Manager adapter in dry-run mode  
python run_simulation.py --dry-run --adapter gam

# See all options
python run_simulation.py --help
```

## Key Features Demonstrated

1. **Command-line arguments** instead of environment variables:
   - `--dry-run`: Enable dry-run mode
   - `--adapter`: Choose adapter (mock, gam, kevel, triton)
   - `--simulation`: Choose simulation type (full, auth)

2. **Adapter-specific API logging**: Each adapter shows exactly what API calls it would make:
   
   **Mock Adapter**:
   ```
   MockAdServer.create_media_buy for principal 'Purina Pet Foods' (adapter ID: mock-purina)
   (dry-run) Would call: MockAdServer.createCampaign()
   (dry-run)   API Request: {
   (dry-run)     'advertiser_id': 'mock-purina',
   (dry-run)     'campaign_name': 'AdCP Campaign buy_PO-DEMO-2025',
   (dry-run)     'budget': 15.0,
   (dry-run)     'targeting': {
   (dry-run)       'geo': ['CA', 'NY'],
   (dry-run)       'exclude_categories': ['controversial']
   (dry-run)     }
   (dry-run)   }
   ```

   **Google Ad Manager**:
   ```
   GoogleAdManager.create_media_buy for principal 'Purina Pet Foods' (GAM advertiser ID: 12345)
   (dry-run) Would call: order_service.createOrders([AdCP Order PO-DEMO-2025])
   (dry-run)   Advertiser ID: 12345
   (dry-run)   Total Budget: $50,000.00
   (dry-run)   Flight Dates: 2025-08-01 to 2025-08-15
   (dry-run) Would call: line_item_service.createLineItems(['Sports Video Package'])
   (dry-run)   Package: Sports Video Package
   (dry-run)   CPM: $15.0
   (dry-run)   Impressions Goal: 3,333,333
   ```

3. **Principal-based adapter mappings**: Each principal has adapter-specific IDs:
   - Mock: `mock-purina`
   - GAM: `12345` 
   - Kevel: `purina-pet-foods`
   - Triton: `ADV-PUR-001`

## Architecture Benefits

- **Separation of concerns**: Each adapter handles its own logging
- **Realistic API simulation**: Shows actual API calls that would be made
- **Easy debugging**: Developers can see exactly what each adapter would do
- **Safe testing**: No actual API calls in dry-run mode

## Running the Demo

```bash
# Quick demo showing both adapters
python demo_dry_run.py

# Full lifecycle simulation with dry-run
python run_simulation.py --dry-run --adapter gam --simulation full
```