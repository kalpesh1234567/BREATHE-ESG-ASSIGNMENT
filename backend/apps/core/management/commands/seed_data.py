"""
Seed command: creates demo org, users, emission factors, and realistic sample data.
Run: python manage.py seed_data

Sample data rationale:
  - SAP MB51: 6 months of diesel + heating oil consumption from two plants (1000, 2000)
    modeled on a mid-sized German manufacturing company. Quantities sized to typical
    industrial use: 500-1200L per forklift/generator fill-up. One reversal posting included.
  - Utility: 6 billing cycles (non-calendar-aligned, e.g. Jan 12 - Feb 11) for two meters
    at different facilities. kWh sized to a medium commercial building (~45,000 kWh/month).
  - Travel: Mix of domestic/international flights, hotel stays, taxis, rental cars.
    Realistic Concur data includes one record with no airport code (flagged as suspicious).
"""
import io
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from apps.core.models import Organization
from apps.ingestion.models import EmissionFactor, IngestionRun
from apps.ingestion.service import ingest_file

User = get_user_model()

# Use str then encode to UTF-8 bytes — avoids SyntaxError with non-ASCII in b"" literals
SAP_CSV = """Materialbel.;Pos.;Buchungsdatum;Bewegungsart;Werk;Lagerort;Materialnummer;Materialbezeichnung;Menge;ME;Betrag HW;Waehrg;Kostenstelle;Auftrag
5000012345;0001;03.01.2024;261;1000;0001;DIESEL-001;Dieselkraftstoff;-500,000;L;-950,00;EUR;KOST-1100;
5000012346;0001;05.01.2024;261;1000;0001;DIESEL-001;Dieselkraftstoff;-320,000;L;-608,00;EUR;;MO-20240001
5000012347;0001;08.01.2024;261;1000;0002;HZOEL-001;Heizoil EL;-1.200,000;L;-1.404,00;EUR;KOST-2200;
5000012348;0001;10.01.2024;101;1000;0001;DIESEL-001;Dieselkraftstoff;5.000,000;L;9.500,00;EUR;;
5000012349;0001;15.01.2024;201;1000;0001;ERDGAS-001;Erdgas;-450,000;m3;-225,00;EUR;KOST-3300;
5000012350;0001;18.01.2024;261;2000;0003;DIESEL-001;Dieselkraftstoff;-280,000;L;-532,00;EUR;KOST-4100;
5000012351;0001;22.01.2024;261;1000;0001;DIESEL-001;Dieselkraftstoff;-410,000;L;-779,00;EUR;KOST-1100;
5000012352;0001;25.01.2024;261;2000;0003;HZOEL-001;Heizoil EL;-890,000;L;-1.041,30;EUR;KOST-4200;
5000012353;0001;31.01.2024;261;1000;0001;DIESEL-001;Dieselkraftstoff;-560,000;L;-1.064,00;EUR;;MO-20240008
5000012354;0001;05.02.2024;261;1000;0001;DIESEL-001;Dieselkraftstoff;-490,000;L;-931,00;EUR;KOST-1100;
5000012355;0001;07.02.2024;261;2000;0003;DIESEL-001;Dieselkraftstoff;-350,000;L;-665,00;EUR;KOST-4100;
5000012356;0001;14.02.2024;261;1000;0002;HZOEL-001;Heizoil EL;-1.100,000;L;-1.287,00;EUR;KOST-2200;
5000012357;0001;19.02.2024;201;1000;0001;ERDGAS-001;Erdgas;-520,000;m3;-260,00;EUR;KOST-3300;
5000012358;0001;28.02.2024;261;1000;0001;DIESEL-001;Dieselkraftstoff;-440,000;L;-836,00;EUR;KOST-1100;
5000012359;0001;04.03.2024;261;2000;0003;DIESEL-001;Dieselkraftstoff;-310,000;L;-589,00;EUR;KOST-4100;
5000012360;0001;11.03.2024;261;1000;0001;DIESEL-001;Dieselkraftstoff;-575,000;L;-1.092,50;EUR;;MO-20240015
5000012361;0001;15.03.2024;261;1000;0002;HZOEL-001;Heizoil EL;-950,000;L;-1.111,50;EUR;KOST-2200;
5000012362;0001;22.03.2024;201;1000;0001;ERDGAS-001;Erdgas;-380,000;m3;-190,00;EUR;KOST-3300;
5000012363;0001;31.03.2024;261;1000;0001;DIESEL-001;Dieselkraftstoff;-620,000;L;-1.178,00;EUR;KOST-1100;
""".encode('utf-8')

UTILITY_CSV = """Account_Number,Meter_ID,Service_Address,Billing_Start,Billing_End,Usage (kWh),Demand (kW),Rate_Schedule,Total_Bill_USD
ACC-00445521,MTR-7712834,123 Industrial Pkwy Plant 1000,2024-01-12,2024-02-11,48250,312.4,GS-3,13542.63
ACC-00445521,MTR-7712834,123 Industrial Pkwy Plant 1000,2024-02-12,2024-03-13,44180,298.7,GS-3,12609.12
ACC-00445521,MTR-7712834,123 Industrial Pkwy Plant 1000,2024-03-14,2024-04-13,51320,341.2,GS-3,14537.22
ACC-00445521,MTR-7712834,123 Industrial Pkwy Plant 1000,2024-04-14,2024-05-13,46800,305.1,GS-3,13204.00
ACC-00445521,MTR-7712834,123 Industrial Pkwy Plant 1000,2024-05-14,2024-06-12,52100,348.9,GS-3,14801.50
ACC-00445521,MTR-7712834,123 Industrial Pkwy Plant 1000,2024-06-13,2024-07-12,58400,390.2,GS-3,16842.00
ACC-00558832,MTR-9934521,456 Commerce Drive Plant 2000,2024-01-18,2024-02-17,32150,215.6,GS-2,8642.25
ACC-00558832,MTR-9934521,456 Commerce Drive Plant 2000,2024-02-18,2024-03-19,29800,199.3,GS-2,7946.00
ACC-00558832,MTR-9934521,456 Commerce Drive Plant 2000,2024-03-20,2024-04-18,33420,222.8,GS-2,8947.50
ACC-00558832,MTR-9934521,456 Commerce Drive Plant 2000,2024-04-19,2024-05-18,31100,207.4,GS-2,8274.00
ACC-00558832,MTR-9934521,456 Commerce Drive Plant 2000,2024-05-19,2024-06-18,35800,238.5,GS-2,9642.00
ACC-00558832,MTR-9934521,456 Commerce Drive Plant 2000,2024-06-19,2024-07-18,41200,274.7,GS-2,11284.00
""".encode('utf-8')

TRAVEL_CSV = """Report_ID,Report_Name,Employee_ID,Employee_Name,Department,Expense_Type,Transaction_Date,Vendor,Amount,Currency,Origin,Destination,Cabin_Class,Nights,Description
EXP-2024-08821,Q1 NYC Client Visit,EMP-4432,Sarah Mitchell,Sales,Airfare,2024-01-15,Delta Air Lines,487.50,USD,BOS,JFK,Economy,,BOS-JFK roundtrip client meeting
EXP-2024-08821,Q1 NYC Client Visit,EMP-4432,Sarah Mitchell,Sales,Lodging,2024-01-15,Marriott Marquis Times Square,298.00,USD,,,,1,Hotel stay NYC 1 night
EXP-2024-08821,Q1 NYC Client Visit,EMP-4432,Sarah Mitchell,Sales,Taxi,2024-01-15,Uber,34.50,USD,,,,,Airport to hotel Manhattan
EXP-2024-09010,Berlin Conference,EMP-2218,James Chen,Operations,Airfare,2024-01-28,Lufthansa,1842.00,USD,ORD,FRA,Business,,ORD-FRA roundtrip business class
EXP-2024-09010,Berlin Conference,EMP-2218,James Chen,Operations,Lodging,2024-01-29,Hilton Berlin,1236.00,EUR,,,,3,3 nights conference Berlin
EXP-2024-09010,Berlin Conference,EMP-2218,James Chen,Operations,Mileage,2024-01-28,Personal Vehicle,12.05,USD,,,,,Drive to ORD airport 18 miles
EXP-2024-09010,Berlin Conference,EMP-2218,James Chen,Operations,Taxi,2024-01-29,Taxi,45.00,EUR,,,,,FRA airport to hotel
EXP-2024-10055,Singapore Sales Trip,EMP-3301,Priya Sharma,Business Dev,Airfare,2024-02-10,Singapore Airlines,2980.00,USD,LHR,SIN,Economy,,LHR-SIN London to Singapore
EXP-2024-10055,Singapore Sales Trip,EMP-3301,Priya Sharma,Business Dev,Lodging,2024-02-11,Marina Bay Sands,890.00,SGD,,,,4,4 nights Singapore
EXP-2024-10055,Singapore Sales Trip,EMP-3301,Priya Sharma,Business Dev,Rental Car,2024-02-14,Avis,340.00,SGD,,,,,Car rental Singapore 4 days
EXP-2024-11203,LA Conference,EMP-5512,Tom Bradley,Engineering,Airfare,2024-02-20,United Airlines,385.00,USD,JFK,LAX,Economy,,New York to LA
EXP-2024-11203,LA Conference,EMP-5512,Tom Bradley,Engineering,Lodging,2024-02-20,Westin Bonaventure,520.00,USD,,,,2,Hotel stay LA 2 nights
EXP-2024-11203,LA Conference,EMP-5512,Tom Bradley,Engineering,Taxi,2024-02-22,Lyft,28.00,USD,,,,,Hotel to LAX
EXP-2024-12099,Client Visit no route info,EMP-6601,Alex Wong,Sales,Airfare,2024-03-05,American Airlines,620.00,USD,,,,Economy,,Flight to client site - no route recorded
EXP-2024-12100,Tokyo Engineering Summit,EMP-2218,James Chen,Operations,Airfare,2024-03-12,ANA,3450.00,USD,ORD,NRT,Business,,Chicago to Tokyo roundtrip business
EXP-2024-12100,Tokyo Engineering Summit,EMP-2218,James Chen,Operations,Lodging,2024-03-13,Park Hyatt Tokyo,2100.00,USD,,,,5,5 nights Tokyo
EXP-2024-12100,Tokyo Engineering Summit,EMP-2218,James Chen,Operations,Taxi,2024-03-13,Taxi,65.00,USD,,,,,NRT airport to Tokyo hotel
""".encode('utf-8')


class Command(BaseCommand):
    help = 'Seed database with demo organization, users, emission factors, and sample data'

    def handle(self, *args, **kwargs):
        self.stdout.write('Seeding BreatheESG demo data...')

        # -- Organization -------------------------------------------------------
        org, created = Organization.objects.get_or_create(
            slug='acme-manufacturing',
            defaults={'name': 'ACME Manufacturing GmbH'}
        )
        self.stdout.write(f'  Org: {org.name} ({"created" if created else "exists"})')

        # -- Users --------------------------------------------------------------
        admin_user, _ = User.objects.get_or_create(
            username='admin',
            defaults={
                'email': 'admin@acme-mfg.com',
                'first_name': 'Admin',
                'last_name': 'User',
                'organization': org,
                'role': 'admin',
                'is_staff': True,
            }
        )
        admin_user.set_password('breatheesg2024')
        admin_user.save()

        analyst_user, _ = User.objects.get_or_create(
            username='analyst',
            defaults={
                'email': 'analyst@acme-mfg.com',
                'first_name': 'Sarah',
                'last_name': 'Green',
                'organization': org,
                'role': 'analyst',
            }
        )
        analyst_user.set_password('breatheesg2024')
        analyst_user.save()
        self.stdout.write('  Users: admin / analyst (password: breatheesg2024)')

        # -- Emission Factors ---------------------------------------------------
        from datetime import date
        factors = [
            # Scope 1 -- Fuels (DEFRA 2024, combustion only / tank-to-wheel)
            dict(category='fuel_diesel', value='2.68', unit='per_liter',
                 source='DEFRA 2024', region='Global', valid_from=date(2024, 1, 1),
                 notes='Diesel EN590. kgCO2e per liter, combustion only (tank-to-wheel). '
                       'Well-to-wheel would be 3.17 kgCO2e/L.'),
            dict(category='fuel_heating_oil', value='2.54', unit='per_liter',
                 source='DEFRA 2024', region='Global', valid_from=date(2024, 1, 1),
                 notes='Light fuel oil / Heizoil EL. kgCO2e per liter.'),
            dict(category='fuel_natural_gas', value='2.04', unit='per_m3',
                 source='DEFRA 2024', region='Global', valid_from=date(2024, 1, 1),
                 notes='Natural gas. kgCO2e per cubic meter at 100% GCV.'),
            dict(category='fuel_petrol', value='2.31', unit='per_liter',
                 source='DEFRA 2024', region='Global', valid_from=date(2024, 1, 1),
                 notes='Petrol/gasoline. kgCO2e per liter.'),
            dict(category='fuel_lpg', value='1.56', unit='per_liter',
                 source='DEFRA 2024', region='Global', valid_from=date(2024, 1, 1),
                 notes='LPG. kgCO2e per liter.'),

            # Scope 2 -- Electricity grid factors (location-based)
            dict(category='electricity_uk', value='0.20707', unit='per_kwh',
                 source='DEFRA/DESNZ 2024', region='UK', valid_from=date(2024, 1, 1),
                 notes='UK National Grid average. Location-based. Market-based may be '
                       'lower if RECs/PPAs are in place.'),
            dict(category='electricity_us', value='0.386', unit='per_kwh',
                 source='EPA eGRID2023', region='US', valid_from=date(2024, 1, 1),
                 notes='US national average. Location-based. Regional grids vary significantly '
                       '(WECC West ~0.27; SERC Southeast ~0.44).'),
            dict(category='electricity_india', value='0.727', unit='per_kwh',
                 source='CEA India 2022', region='IN', valid_from=date(2024, 1, 1),
                 notes='India national grid. High due to coal dependence.'),
            dict(category='electricity_eu', value='0.295', unit='per_kwh',
                 source='IEA 2022', region='EU', valid_from=date(2024, 1, 1),
                 notes='EU average. France is ~0.052 (nuclear); Germany ~0.380.'),

            # Scope 3 -- Air travel (DEFRA 2024, includes 1.7x Radiative Forcing uplift)
            dict(category='flight_economy_domestic', value='0.24531', unit='per_pkm',
                 source='DEFRA 2024', region='Global', valid_from=date(2024, 1, 1),
                 notes='Economy class, domestic (<500km). Includes 1.7x RF uplift.'),
            dict(category='flight_economy_shorthaul', value='0.12576', unit='per_pkm',
                 source='DEFRA 2024', region='Global', valid_from=date(2024, 1, 1),
                 notes='Economy class, short-haul (500-3700km). Includes 1.7x RF uplift.'),
            dict(category='flight_economy_longhaul', value='0.11704', unit='per_pkm',
                 source='DEFRA 2024', region='Global', valid_from=date(2024, 1, 1),
                 notes='Economy class, long-haul (>3700km). Includes 1.7x RF uplift.'),
            dict(category='flight_business_shorthaul', value='0.18864', unit='per_pkm',
                 source='DEFRA 2024', region='Global', valid_from=date(2024, 1, 1),
                 notes='Business class, short-haul. Includes 1.7x RF uplift.'),
            dict(category='flight_business_longhaul', value='0.42954', unit='per_pkm',
                 source='DEFRA 2024', region='Global', valid_from=date(2024, 1, 1),
                 notes='Business class, long-haul. Higher per-pkm due to seat footprint. '
                       'Includes 1.7x RF uplift.'),
            dict(category='flight_premium_economy_longhaul', value='0.18726', unit='per_pkm',
                 source='DEFRA 2024', region='Global', valid_from=date(2024, 1, 1),
                 notes='Premium economy, long-haul. Includes 1.7x RF uplift.'),
            dict(category='flight_first_longhaul', value='0.54779', unit='per_pkm',
                 source='DEFRA 2024', region='Global', valid_from=date(2024, 1, 1),
                 notes='First class, long-haul. Highest per-pkm. Includes 1.7x RF uplift.'),

            # Scope 3 -- Hotels
            dict(category='hotel_stay', value='21.4', unit='per_room_night',
                 source='DEFRA 2024', region='Global', valid_from=date(2024, 1, 1),
                 notes='Average hotel room night. Range is wide (budget: ~10, luxury: ~50). '
                       'This is the DEFRA global average. HCMI methodology offers property-level data.'),

            # Scope 3 -- Ground transport
            dict(category='ground_rental_car', value='0.192', unit='per_km',
                 source='DEFRA 2024', region='Global', valid_from=date(2024, 1, 1),
                 notes='Average rental car (petrol, medium). kgCO2e per km.'),
            dict(category='ground_personal_car', value='0.170', unit='per_km',
                 source='DEFRA 2024', region='Global', valid_from=date(2024, 1, 1),
                 notes='Average personal car (petrol). kgCO2e per km.'),
            dict(category='ground_taxi', value='0.214', unit='per_km',
                 source='DEFRA 2024', region='Global', valid_from=date(2024, 1, 1),
                 notes='Taxi/rideshare average. kgCO2e per km.'),
            dict(category='ground_train', value='0.035', unit='per_pkm',
                 source='DEFRA 2024', region='UK', valid_from=date(2024, 1, 1),
                 notes='UK national rail average. kgCO2e per passenger-km.'),
            dict(category='ground_bus', value='0.027', unit='per_pkm',
                 source='DEFRA 2024', region='UK', valid_from=date(2024, 1, 1),
                 notes='Coach/bus average. kgCO2e per passenger-km.'),
        ]

        for f in factors:
            EmissionFactor.objects.get_or_create(
                category=f['category'],
                valid_to__isnull=True,
                defaults=f,
            )
        self.stdout.write(f'  Emission factors: {len(factors)} seeded')

        # -- Sample Data --------------------------------------------------------
        if IngestionRun.objects.filter(organization=org).exists():
            self.stdout.write('  Sample data already exists -- skipping ingestion')
            self.stdout.write(self.style.SUCCESS('\nSeed complete!'))
            return

        sources = [
            (IngestionRun.SOURCE_SAP_FUEL, 'sap_mb51_jan_mar_2024.csv', SAP_CSV),
            (IngestionRun.SOURCE_UTILITY, 'utility_electricity_h1_2024.csv', UTILITY_CSV),
            (IngestionRun.SOURCE_TRAVEL, 'concur_travel_q1_2024.csv', TRAVEL_CSV),
        ]

        for source_type, filename, content in sources:
            run = IngestionRun.objects.create(
                organization=org,
                uploaded_by=admin_user,
                source_type=source_type,
                filename=filename,
            )
            ingest_file(run, content, admin_user)
            self.stdout.write(
                f'  Ingested {filename}: {run.parsed_count} records, {run.error_count} errors'
            )

        self.stdout.write(self.style.SUCCESS('\nSeed complete! Login: admin / breatheesg2024'))
