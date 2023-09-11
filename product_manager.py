import stripe
import os
from examples import fruit_dict

STRIPE_KEY = os.environ.get("STRIPE_API_KEY")
stripe.api_key = STRIPE_KEY


# I first created my products and prices by running this script on main.py
def create_products():
    if not stripe.Price.list().to_dict()["data"]:
        for fruit in fruit_dict:
            stripe.Product.create(name=fruit, images=[fruit_dict[fruit]['image']], id=fruit)
            stripe.Price.create(
                product=fruit,
                currency="usd",
                billing_scheme="per_unit",
                unit_amount_decimal=str(fruit_dict[fruit]['price'] * 100)
            )


# Then this function is used inside main.py to add the price_id to the fruit_dict
def get_fruits():
    stripe_data = stripe.Price.list().to_dict()["data"]
    stripe_data_dict = {key['product']: key['id'] for key in stripe_data}
    for fruit in fruit_dict:
        if fruit in stripe_data_dict:
            fruit_dict[fruit]['price_id'] = stripe_data_dict[fruit]
    return fruit_dict
