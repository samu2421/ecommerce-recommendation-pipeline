import os
from collections import defaultdict

import pandas as pd
from flask import Flask, jsonify, request
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from sklearn.metrics.pairwise import cosine_similarity

DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql+psycopg2://samiksha:password123@localhost:5432/ecommerce_data"
)
MAX_RECOMMENDATIONS = 10
DEFAULT_RECOMMENDATIONS = 5
SIMILAR_USERS = 5

app = Flask(__name__)
CORS(app)

app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)


class SalesData(db.Model):
    """Read-only mapping of the sales_data table created by init_postgres.sql."""
    __tablename__ = 'sales_data'

    InvoiceNo = db.Column(db.String(20), primary_key=True)
    StockCode = db.Column(db.String(20))
    Description = db.Column(db.Text)
    Quantity = db.Column(db.Integer)
    InvoiceDate = db.Column(db.DateTime)
    UnitPrice = db.Column(db.Numeric(10, 2))
    CustomerID = db.Column(db.String(20))
    Country = db.Column(db.String(50))


class ModelNotTrainedError(Exception):
    pass


def normalize_customer_id(value):
    """Treat 17850, "17850" and "17850.0" as the same customer; missing -> None."""
    if value is None or pd.isna(value):
        return None
    text = str(value).strip()
    if text.endswith(".0"):
        text = text[:-2]
    return text or None


def clamp_n(n):
    return max(1, min(int(n), MAX_RECOMMENDATIONS))


class RecommendationEngine:
    """User-based collaborative filtering on a customer x product quantity matrix."""

    def __init__(self):
        self.user_item_matrix = None
        self.similarity_matrix = None
        self.descriptions = {}
        self.popular_products = []

    @property
    def is_trained(self):
        return self.user_item_matrix is not None

    def train(self):
        """Load all sales from PostgreSQL and fit the model."""
        sales_df = pd.read_sql(db.session.query(SalesData).statement, db.engine)
        self.fit(sales_df)

    def fit(self, sales_df):
        """Fit from a DataFrame with CustomerID, StockCode, Description and Quantity columns."""
        df = sales_df[['CustomerID', 'StockCode', 'Description', 'Quantity']].copy()
        df['CustomerID'] = df['CustomerID'].map(normalize_customer_id)

        # Net quantities: cancellations (negative rows) cancel out the original
        # purchase. Only positive net totals count as "bought". Anonymous rows
        # cannot be attributed to a customer, so they are left out of the matrix.
        customer_rows = df[df['CustomerID'].notna()]
        net = customer_rows.groupby(['CustomerID', 'StockCode'])['Quantity'].sum()
        net = net[net > 0]
        if net.empty:
            raise ValueError("No sales data available to train the model.")

        user_item = net.unstack(fill_value=0)
        self.similarity_matrix = cosine_similarity(user_item)
        self.user_item_matrix = user_item

        self.descriptions = (
            df.dropna(subset=['Description'])
              .drop_duplicates('StockCode')
              .set_index('StockCode')['Description']
              .to_dict()
        )

        # Fallback for unknown customers, computed once here, not per request:
        # net quantity per product across all rows (anonymous sales included).
        net_per_product = df.groupby('StockCode')['Quantity'].sum()
        popular = net_per_product[net_per_product > 0].nlargest(MAX_RECOMMENDATIONS)
        self.popular_products = [self._product(code, qty) for code, qty in popular.items()]
        return self

    def _product(self, stock_code, score):
        return {
            'stock_code': str(stock_code),
            'description': self.descriptions.get(stock_code, ''),
            'score': float(score),
        }

    def get_recommendations(self, customer_id, n_recommendations=DEFAULT_RECOMMENDATIONS):
        if not self.is_trained:
            raise ModelNotTrainedError("Model is not trained yet. Call POST /train first.")
        n = clamp_n(n_recommendations)
        customer_id = normalize_customer_id(customer_id)

        if customer_id not in self.user_item_matrix.index:
            return self.popular_products[:n]

        user_idx = self.user_item_matrix.index.get_loc(customer_id)
        similarities = self.similarity_matrix[user_idx]
        similar_users = [i for i in similarities.argsort()[::-1] if i != user_idx][:SIMILAR_USERS]

        # Products this customer already owns (positive net quantity) are not recommended
        own = self.user_item_matrix.iloc[user_idx]
        already_bought = set(own[own > 0].index)

        scores = defaultdict(float)
        for idx in similar_users:
            purchases = self.user_item_matrix.iloc[idx]
            for product, quantity in purchases[purchases > 0].items():
                if product not in already_bought:
                    scores[product] += similarities[idx] * quantity

        top = sorted(scores.items(), key=lambda item: item[1], reverse=True)[:n]
        return [self._product(code, score) for code, score in top]


recommendation_engine = RecommendationEngine()


@app.route('/test', methods=['GET'])
def test():
    return jsonify({'message': 'The Flask app is running!'}), 200


@app.route('/train', methods=['POST'])
def train_model():
    try:
        recommendation_engine.train()
        return jsonify({
            'message': 'Model trained successfully',
            'customers': int(recommendation_engine.user_item_matrix.shape[0]),
            'products': int(recommendation_engine.user_item_matrix.shape[1]),
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/recommendations/<string:customer_id>', methods=['GET'])
def get_recommendations(customer_id):
    try:
        n = int(request.args.get('n', DEFAULT_RECOMMENDATIONS))
    except ValueError:
        return jsonify({'error': 'n must be an integer between 1 and 10'}), 400
    try:
        return jsonify(recommendation_engine.get_recommendations(customer_id, n)), 200
    except ModelNotTrainedError as e:
        return jsonify({'error': str(e)}), 503
    except Exception as e:
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    debug = os.getenv("FLASK_DEBUG", "0").lower() in ("1", "true", "yes")
    host = os.getenv("FLASK_HOST", "127.0.0.1")
    port = int(os.getenv("FLASK_PORT", "5001"))
    app.run(debug=debug, host=host, port=port)
