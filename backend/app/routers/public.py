"""General dashboards - open to everyone (no login)."""
from fastapi import APIRouter, Query

from ..db import query, records, scalar

router = APIRouter(prefix="/api/public", tags=["public dashboards"])

# Years where fewer than this share of states reported are flagged as incomplete,
# so a coverage drop is not misread as a real collapse in production.
COVERAGE_THRESHOLD = 0.8


@router.get("/overview")
def overview():
    crop_years = query("SELECT min(year) a, max(year) b, count(DISTINCT state) s, count(DISTINCT crop) c FROM crop").iloc[0]
    sui = query("SELECT min(year) a, max(year) b, sum(total) t FROM suicides_headline").iloc[0]
    rain = query("SELECT min(year) a, max(year) b, count(DISTINCT subdivision) s FROM rainfall").iloc[0]
    dia = query("SELECT count(*) n, avg(diabetes) p FROM diabetes").iloc[0]
    wx = query("SELECT min(date) a, max(date) b, count(DISTINCT city) c FROM weather").iloc[0]
    return {"cards": [
        {"key": "crop", "title": "Crop production", "span": f"{int(crop_years.a)}-{int(crop_years.b)}",
         "facts": [f"{crop_years.s} states/UTs", f"{crop_years.c} crops", "district level"]},
        {"key": "rainfall", "title": "Rainfall", "span": f"{int(rain.a)}-{int(rain.b)}",
         "facts": [f"{rain.s} IMD sub-divisions", "monthly totals", "115 years"]},
        {"key": "suicides", "title": "Suicides (NCRB)", "span": f"{int(sui.a)}-{int(sui.b)}",
         "facts": [f"{int(sui.t):,} recorded deaths", "by state, gender, age", "5 breakdowns"]},
        {"key": "diabetes", "title": "Diabetes indicators", "span": "cross-sectional",
         "facts": [f"{int(dia.n):,} records", f"{100 * dia.p:.1f}% diabetic", "8 health indicators"]},
        {"key": "weather", "title": "City weather", "span": f"{wx.a.year}-{wx.b.year}",
         "facts": [f"{wx.c} cities", "daily", "temperature, rain, wind"]},
    ]}


# ------------------------------------------------------------------ crop
@router.get("/crop")
def crop():
    max_states = scalar("SELECT count(DISTINCT state) FROM crop")
    yearly = query("""
        SELECT year, sum(production) AS production_t, sum(area_ha) AS area_ha, count(DISTINCT state) AS states_reporting
        FROM crop WHERE unit = 'tonnes' GROUP BY year ORDER BY year""")
    yearly["complete"] = yearly["states_reporting"] >= COVERAGE_THRESHOLD * max_states
    top_crops = query("""
        SELECT crop, sum(production) / count(DISTINCT year) AS avg_annual_t
        FROM crop WHERE unit = 'tonnes' GROUP BY crop ORDER BY avg_annual_t DESC LIMIT 10""")
    states = query("""
        SELECT state, sum(production) / count(DISTINCT year) AS avg_annual_t, sum(area_ha) / count(DISTINCT year) AS avg_area_ha
        FROM crop WHERE unit = 'tonnes' GROUP BY state ORDER BY avg_annual_t DESC""")
    seasons = query("""
        SELECT season, sum(area_ha) / count(DISTINCT year) AS avg_area_ha FROM crop
        GROUP BY season ORDER BY avg_area_ha DESC""")
    return {"yearly": records(yearly), "top_crops": records(top_crops), "states": records(states),
            "seasons": records(seasons), "max_states": max_states,
            "notes": ["Totals include only crops measured in tonnes (coconut and fibre crops excluded)",
                      "Aggregate rows such as 'Total foodgrain' are excluded to avoid double counting",
                      "Faded bars mark years where under 80% of states reported - totals there are NOT comparable"]}


# ------------------------------------------------------------------ rainfall
@router.get("/rainfall")
def rainfall():
    india = query("""
        SELECT year, avg(annual) AS annual_mm, avg(jun_sep) AS monsoon_mm, avg(departure_pct) AS departure_pct,
               count(*) AS subdivisions
        FROM rainfall GROUP BY year ORDER BY year""")
    subs = query("""
        SELECT subdivision, avg(annual) AS mean_annual_mm, avg(jun_sep) AS mean_monsoon_mm
        FROM rainfall GROUP BY subdivision ORDER BY mean_annual_mm DESC""")
    monthly = query("""
        SELECT avg(jan) jan, avg(feb) feb, avg(mar) mar, avg(apr) apr, avg(may) may, avg(jun) jun,
               avg(jul) jul, avg(aug) aug, avg(sep) sep, avg(oct) oct, avg(nov) nov, avg("dec") "dec" FROM rainfall""")
    months = [{"month": k.capitalize(), "mm": v} for k, v in records(monthly)[0].items()]
    return {"india": records(india), "subdivisions": records(subs), "monthly": months,
            "notes": ["'India' is the simple mean of IMD sub-divisions, not an area-weighted national figure",
                      "Departure % is relative to each sub-division's 1961-2010 average"]}


# ------------------------------------------------------------------ suicides
@router.get("/suicides")
def suicides():
    yearly = query("""SELECT year, sum(total) total,
                             sum(total) FILTER (WHERE gender='Male') male,
                             sum(total) FILTER (WHERE gender='Female') female
                      FROM suicides_headline GROUP BY year ORDER BY year""")
    states = query("""SELECT state, sum(total) total FROM suicides_headline WHERE year = 2012
                      GROUP BY state ORDER BY total DESC""")
    ages = query("""SELECT age_group, sum(total) total FROM suicides_headline
                    GROUP BY age_group ORDER BY age_group""")
    return {"yearly": records(yearly), "states_2012": records(states), "age_groups": records(ages),
            "notes": ["Counts, not rates: population data is not part of this dataset, so large states naturally rank higher",
                      "Totals come from one breakdown (means adopted) - other breakdowns describe the same deaths",
                      "If you or someone you know is struggling, call Tele-MANAS 14416 (India, 24x7, free)"]}


# ------------------------------------------------------------------ diabetes
@router.get("/diabetes")
def diabetes():
    def prevalence(col):
        return records(query(f"""SELECT {col} AS grp, count(*) n, avg(diabetes) * 100 AS prevalence_pct
                                 FROM diabetes GROUP BY {col} ORDER BY {col}"""))
    overall = query("SELECT count(*) n, avg(diabetes) * 100 p, avg(bmi) bmi, avg(HbA1c_level) hba1c FROM diabetes").iloc[0]
    return {"overall": {"records": int(overall.n), "prevalence_pct": round(overall.p, 2),
                        "mean_bmi": round(overall.bmi, 1), "mean_hba1c": round(overall.hba1c, 2)},
            "by_age": prevalence("age_band"), "by_bmi": prevalence("bmi_class"),
            "by_gender": prevalence("gender"), "by_smoking": prevalence("smoking_history"),
            "notes": ["This dataset is not specific to India and its sampling method is undocumented",
                      "Prevalence here describes this sample only, not the national population",
                      "3,854 exact duplicate records were removed before analysis"]}


# ------------------------------------------------------------------ weather
@router.get("/weather")
def weather(city: str = Query("Delhi")):
    cities = [r["city"] for r in records(query("SELECT DISTINCT city FROM weather ORDER BY city"))]
    monthly = query("""SELECT month, avg(temperature_2m_max) tmax, avg(temperature_2m_min) tmin,
                              sum(precipitation_sum) / count(DISTINCT year) rain_mm
                       FROM weather WHERE city = ? GROUP BY month ORDER BY month""", [city])
    yearly = query("""SELECT year, avg(temperature_2m_max) mean_tmax, sum(precipitation_sum) rain_mm,
                             sum(rainy_day) rainy_days
                      FROM weather WHERE city = ? GROUP BY year ORDER BY year""", [city])
    compare = query("""SELECT city, avg(temperature_2m_max) mean_tmax, sum(precipitation_sum) / count(DISTINCT year) annual_rain_mm
                       FROM weather GROUP BY city ORDER BY mean_tmax DESC""")
    return {"cities": cities, "city": city, "monthly": records(monthly), "yearly": records(yearly),
            "compare": records(compare),
            "notes": ["Source: ERA5 reanalysis via Open-Meteo - a grid estimate, not a weather station",
                      "Rainy day = 2.5 mm or more in 24 hours (IMD definition)"]}
