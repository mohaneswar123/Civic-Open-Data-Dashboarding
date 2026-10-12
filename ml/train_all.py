"""Train every model:  python -m ml.train_all"""
from ml import train_crop, train_diabetes, train_suicides, train_weather

if __name__ == "__main__":
    for name, mod in [("crop", train_crop), ("suicides", train_suicides),
                      ("diabetes", train_diabetes), ("weather", train_weather)]:
        print(f"=== {name} ===")
        mod.main()
