import pandas as pd
import numpy as np
import random
from datetime import datetime, timedelta

# Create synthetic data for a pharmacy selling drugs
def generate_dirty_pharma_data(num_rows=100):
    # Set seed for reproducibility
    np.random.seed(42)
    random.seed(42)

    # Lists for generation
    drugs = [
        "Amoxicillin", "Paracetamol", "Ibuprofen", "Metformin", "Atorvastatin",
        "Aspirin", "Omeprazole", "Lisinopril", "Azithromycin", "Sertraline",
        "Vitamin C", "Insulin", "Ventolin", "Ciprofloxacin", "Gabapentin"
    ]
    categories = ["Antibiotics", "Analgesics", "Antidiabetic", "Cardiovascular", "Gastrointestinal", "Vitamins", "Respiratory"]
    locations = ["New York", "Chicago", "Houston", "Phoenix", "Philadelphia", "San Antonio", "San Diego"]
    pharmacists = ["Dr. Smith", "Dr. Johnson", "Dr. Williams", "Dr. Brown", "Dr. Jones"]

    data = []
    
    start_date = datetime(2023, 1, 1)

    for i in range(num_rows):
        # 1. Transaction ID
        tx_id = f"TXN-{1000 + i}"
        
        # 2. Date
        date_obj = start_date + timedelta(days=random.randint(0, 365), hours=random.randint(0, 23))
        
        # Introduce Date Issues (5% probability)
        if random.random() < 0.05:
            date_val = random.choice([None, "00-00-2023", "2023/13/45", "Invalid Date"])
        elif random.random() < 0.05:
            # Different format
            date_val = date_obj.strftime("%d-%m-%Y")
        else:
            date_val = date_obj.strftime("%Y-%m-%d")

        # 3. Drug Name
        drug = random.choice(drugs)
        # Inconsistency in casing (5%)
        if random.random() < 0.05:
            drug = drug.upper() if random.random() > 0.5 else drug.lower()
        # Typos (3%)
        if random.random() < 0.03:
            drug = drug[:-1] + "x"

        # 4. Category
        category = random.choice(categories)
        # Missing category (3%)
        if random.random() < 0.03:
            category = np.nan

        # 5. Quantity
        quantity = random.randint(1, 10)
        # Outliers/Issues (5%)
        if random.random() < 0.05:
            quantity = random.choice([-5, 9999, "ten", None])

        # 6. Unit Price
        unit_price = round(random.uniform(5.0, 150.0), 2)
        # String instead of float (2%)
        if random.random() < 0.02:
            unit_price = f"${unit_price}"
        # Missing (3%)
        if random.random() < 0.03:
            unit_price = None

        # 7. Total Price (calculated)
        try:
            total_price = float(quantity) * float(str(unit_price).replace('$', ''))
        except (ValueError, TypeError):
            total_price = 0.0
        
        # Calculated wrongly on purpose (2%)
        if random.random() < 0.02:
            total_price = total_price * 1.5

        # 8. Location
        location = random.choice(locations)
        # Abbreviations vs full name (5%)
        if location == "New York" and random.random() < 0.5:
            location = "NY"

        # 9. Customer Name
        customer = f"Customer_{random.randint(1, 200)}"
        if random.random() < 0.02:
            customer = None

        data.append({
            "Transaction_ID": tx_id,
            "Date": date_val,
            "Customer_Name": customer,
            "Drug_Name": drug,
            "Category": category,
            "Quantity": quantity,
            "Unit_Price": unit_price,
            "Total_Price": round(total_price, 2) if isinstance(total_price, float) else total_price,
            "Location": location,
            "Pharmacist": random.choice(pharmacists)
        })

    # Add Duplicates (approx 20 rows)
    duplicates = random.sample(data, 20)
    data.extend(duplicates)

    df = pd.DataFrame(data)
    
    # Shuffle the dataframe
    df = df.sample(frac=1).reset_index(drop=True)
    
    # Save to CSV
    filename = "pharma_sales_data_dirty.csv"
    df.to_csv(filename, index=False)
    print(f"Generated {len(df)} rows of data and saved to {filename}")
    return df

if __name__ == "__main__":
    generate_dirty_pharma_data(100)
