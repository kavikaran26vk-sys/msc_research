import json
import os
from database import engine, SessionLocal, Base, Cluster, Product

def load_clusters(json_path="matched_clusters.json"):
    # Create tables
    Base.metadata.create_all(engine)
    db = SessionLocal()

    try:
        # Clear existing data
        db.query(Product).delete()
        db.query(Cluster).delete()
        db.commit()

        with open(json_path, "r", encoding="utf-8") as f:
            clusters = json.load(f)

        print(f"Loading {len(clusters)} clusters...")

        for c in clusters:
            cluster = Cluster(
                cluster_id     = c["cluster_id"],
                product_count  = c["product_count"],
                retailer_count = len(c["retailers"]),
                retailers      = ",".join(c["retailers"]),
                best_price     = c["best_price"],
                best_retailer  = c["best_retailer"],
            )
            db.add(cluster)

            for p in c["products"]:
                product = Product(
                    global_id    = p["global_id"],
                    cluster_id   = c["cluster_id"],
                    retailer     = p.get("retailer", ""),
                    name         = p.get("name", ""),
                    brand        = p.get("brand", ""),
                    price        = p.get("price", 0.0),
                    price_str    = p.get("price_str", ""),
                    ram          = p.get("ram", ""),
                    storage      = p.get("storage", ""),
                    screen_size  = p.get("screen_size", ""),
                    processor    = p.get("processor", ""),
                    gpu          = p.get("gpu", ""),
                    url          = p.get("url", ""),
                    stock_status = p.get("stock_status", ""),
                )
                db.add(product)

        db.commit()
        print(f"✅ Loaded successfully!")
        print(f"   Clusters : {db.query(Cluster).count()}")
        print(f"   Products : {db.query(Product).count()}")

    except Exception as e:
        db.rollback()
        print(f"Error: {e}")
        raise
    finally:
        db.close()

if __name__ == "__main__":
    load_clusters()