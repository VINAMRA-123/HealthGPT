
from app.ai.agents.nutrition_validator import validate_meals

test_meals = [
    {
        "food_name": "Paneer",
        "calories": 265,
        "protein_g": 18,
        "carbs_g": 6,
        "fat_g": 20,
    },
    {
        "food_name": "Suspicious Poha",
        "calories": 10,
        "protein_g": 20,
        "carbs_g": 10,
        "fat_g": 30,
    },
    {
        "food_name": "Incomplete Meal",
        "calories": 200,
        "protein_g": None,
        "carbs_g": 30,
        "fat_g": 5,
    },
]

results = validate_meals(test_meals)

for meal in results:
    print("\nFood:", meal["food_name"])
    print("Status:", meal["data_quality_status"])
    print("Warnings:", meal["data_quality_warnings"])
