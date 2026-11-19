# create_sample_data.py
def create_sample_data():
    sample_data = [
        "6.5\t45.0\t25.0\t30.0\t200",
        "6.7\t46.2\t25.5\t32.1\t210", 
        "7.0\t47.8\t26.1\t35.6\t195",
        "6.8\t44.5\t24.8\t31.2\t205",
        "27.52\t22.24\t21.90\t55.29\t556.17"
    ]
    
    with open('sensor_data.txt', 'w') as file:
        file.write('\n'.join(sample_data))
    
    print("Sample sensor_data.txt created successfully!")

if __name__ == "__main__":
    create_sample_data()
