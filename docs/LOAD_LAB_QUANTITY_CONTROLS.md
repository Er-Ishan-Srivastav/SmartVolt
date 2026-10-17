# Load Lab quantity controls

## Appliance board

- Choose a unit count from 1 to 100 on each appliance card before turning it on.
- A running appliance's quantity can be changed with **Apply N units**.
- Per-unit wattage remains fixed by the catalogue; effective live watts are `unit watts × quantity`.
- The simulation tick accumulates energy using effective wattage, so wallet debits scale with the number of units.

## Daily load template

Each appliance row defines:

- **Quantity**: 0–100 units. Zero excludes that appliance from the template.
- **Start time**: local clock time, editable to the minute.
- **Runtime**: hours per day in 15-minute increments. Zero excludes the appliance.

The builder previews estimated daily kWh and cost using the selected meter's tariff. A schedule crossing midnight is split into a late-day block and an after-midnight block. Newly saved blocks record their per-appliance quantities in `appliance_quantities`.

For compatibility, older built-in and saved templates that don't contain `appliance_quantities` use one unit per listed appliance. The server validates quantities in the 1–100 range and validates that quantity keys correspond to appliance IDs in the same schedule block.

## Database migration and rollout

Migration `0007_appliance_quantities` adds a non-null integer `quantity` column to `active_appliances` with a server default of `1`; current live loads are therefore preserved as one unit each. The production API runs Alembic upgrades on startup. Do not delete the PostgreSQL Docker volume during deployment.

After deployment, verify the API health endpoint, test the appliance board, create a test template with multiple units, and compare the displayed estimated kWh to the resulting scenario reading in a test meter before using live room balances.
