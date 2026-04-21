import json
import time
import requests
from datetime import datetime

API_URL    = "http://localhost:8000/query"
OUTPUT     = "phase4_evaluation_results.json"

TEST_QUERIES = [
    {"id": "G1", "category": "Gaming",   "query": "I need a gaming laptop under £800",                    "followup": None},
    {"id": "G2", "category": "Gaming",   "query": "gaming laptop with RTX graphics 16GB RAM",             "followup": "around £900"},
    {"id": "G3", "category": "Gaming",   "query": "best gaming laptop around 1000 pounds",                "followup": None},
    {"id": "G4", "category": "Gaming",   "query": "laptop for playing games like FIFA and GTA",           "followup": "around £700"},
    {"id": "S1", "category": "Student",  "query": "laptop for university under £500",                     "followup": None},
    {"id": "S2", "category": "Student",  "query": "I need something for studying and taking notes",       "followup": "around £400"},
    {"id": "S3", "category": "Student",  "query": "cheap laptop for uni around 400 pounds",               "followup": None},
    {"id": "S4", "category": "Student",  "query": "lightweight laptop for student",                       "followup": "under £500"},
    {"id": "B1", "category": "Business", "query": "business laptop with 16GB RAM",                        "followup": "under £700"},
    {"id": "B2", "category": "Business", "query": "professional laptop for office work",                  "followup": "around £600"},
    {"id": "B3", "category": "Business", "query": "work laptop under £700 good for meetings",             "followup": None},
    {"id": "B4", "category": "Business", "query": "laptop for working from home with video calls",        "followup": "under £600"},
    {"id": "U1", "category": "Budget",   "query": "cheapest laptop under £400",                           "followup": None},
    {"id": "U2", "category": "Budget",   "query": "basic laptop just for browsing and emails",            "followup": "under £350"},
    {"id": "U3", "category": "Budget",   "query": "affordable laptop around 300 pounds",                  "followup": None},
    {"id": "U4", "category": "Budget",   "query": "entry level laptop nothing fancy",                     "followup": "around £400"},
    {"id": "V1", "category": "Vague",    "query": "I need a laptop",                                      "followup": "for everyday use around £500"},
    {"id": "V2", "category": "Vague",    "query": "recommend me something good",                          "followup": "student use around £450"},
    {"id": "V3", "category": "Vague",    "query": "something not too expensive for everyday use",         "followup": "around £400"},
    {"id": "V4", "category": "Vague",    "query": "laptop for a mum who just wants to browse",            "followup": "under £400"},
]


def send_query(query: str, session_id: str) -> dict:
    response = requests.post(
        API_URL,
        json={"query": query, "session_id": session_id},
        timeout=60
    )
    return response.json()


def run_evaluation():
    print("=" * 60)
    print("PHASE 4 — AGENT EVALUATION")
    print("=" * 60)

    results        = []
    response_times = []

    for i, test in enumerate(TEST_QUERIES, 1):
        # ✅ Fresh session per query
        session_id = f"eval_{test['id']}_{int(time.time())}"
        print(f"\n[{i:02d}/20] {test['id']} — {test['query'][:55]}")

        total_start = time.time()

        try:
            # ── Turn 1 — Initial query ──────────────────────────
            t1_start = time.time()
            data     = send_query(test["query"], session_id)
            t1_time  = round(time.time() - t1_start, 2)

            recs          = data.get("recommendations", [])
            clarification = data.get("clarification_needed", False)

            print(f"  Turn 1: {t1_time}s | Recs: {len(recs)} | Clarification: {clarification}")

            if clarification and data.get("clarification_question"):
                print(f"  Agent asked: {data['clarification_question'][:70]}")

            # ── Turn 2 — Follow-up if clarification needed ──────
            if (not recs) and test.get("followup"):
                followup = test["followup"]
                print(f"  Turn 2: sending followup → '{followup}'")

                t2_start = time.time()
                data2    = send_query(followup, session_id)
                t2_time  = round(time.time() - t2_start, 2)

                recs          = data2.get("recommendations", [])
                clarification = data2.get("clarification_needed", False)
                data          = data2  # use final response

                print(f"  Turn 2: {t2_time}s | Recs: {len(recs)} | Clarification: {clarification}")

            # ── Turn 3 — One more try if still empty ────────────
            if (not recs) and clarification:
                print(f"  Turn 3: sending generic followup")
                t3_start = time.time()
                data3    = send_query("around £500 for general use", session_id)
                t3_time  = round(time.time() - t3_start, 2)

                recs          = data3.get("recommendations", [])
                clarification = data3.get("clarification_needed", False)
                data          = data3

                print(f"  Turn 3: {t3_time}s | Recs: {len(recs)}")

            total_time = round(time.time() - total_start, 2)
            response_times.append(total_time)

            multi_retailer_cnt = sum(1 for r in recs if r.get("is_multi_retailer"))

            if recs:
                top = recs[0]
                print(f"  ✅ Top: {top['name'][:55]} — {top['price_str']}")
            else:
                print(f"  ❌ No recommendations returned")

            result = {
                "id"                  : test["id"],
                "category"            : test["category"],
                "query"               : test["query"],
                "followup_used"       : test.get("followup") if not recs else None,
                "total_time_secs"     : total_time,
                "rec_count"           : len(recs),
                "clarification_needed": clarification,
                "multi_retailer_count": multi_retailer_cnt,
                "reasoning"           : data.get("reasoning", ""),
                "recommendations"     : recs,
                "timestamp"           : datetime.now().isoformat(),
                "manual_scores": {
                    "relevance"        : None,
                    "price_accuracy"   : None,
                    "reasoning_quality": None,
                    "notes"            : ""
                }
            }

        except Exception as e:
            total_time = round(time.time() - total_start, 2)
            response_times.append(total_time)
            print(f"  ❌ ERROR: {e}")
            result = {
                "id"                  : test["id"],
                "category"            : test["category"],
                "query"               : test["query"],
                "total_time_secs"     : total_time,
                "rec_count"           : 0,
                "clarification_needed": False,
                "multi_retailer_count": 0,
                "reasoning"           : "",
                "recommendations"     : [],
                "error"               : str(e),
                "timestamp"           : datetime.now().isoformat(),
                "manual_scores": {
                    "relevance"        : None,
                    "price_accuracy"   : None,
                    "reasoning_quality": None,
                    "notes"            : ""
                }
            }

        results.append(result)
        time.sleep(2)

    # ── Summary ─────────────────────────────────────────────
    successful = [r for r in results if r["rec_count"] > 0]
    avg_time   = round(sum(response_times) / len(response_times), 2)

    summary = {
        "total_queries"       : len(TEST_QUERIES),
        "successful_queries"  : len(successful),
        "failed_queries"      : len(TEST_QUERIES) - len(successful),
        "avg_response_time"   : avg_time,
        "min_response_time"   : min(response_times),
        "max_response_time"   : max(response_times),
        "all_response_times"  : response_times,
        "clarification_count" : sum(1 for r in results if r["clarification_needed"]),
        "multi_retailer_shown": sum(r["multi_retailer_count"] for r in results),
        "run_timestamp"       : datetime.now().isoformat(),
    }

    output = {
        "summary"       : summary,
        "scoring_rubric": """
RELEVANCE (1-5):
  5 = All top 3 results perfectly match use case and budget
  4 = Most results match, minor issues
  3 = Some results match but some are off
  2 = Few results match
  1 = Results don't match at all

PRICE ACCURACY (1-5):
  5 = All results within stated budget
  4 = Most within budget, 1 slightly over
  3 = Half within budget
  2 = Few within budget
  1 = Most over budget

REASONING QUALITY (1-5):
  5 = Clear, specific, explains why each laptop suits user
  4 = Good reasoning, minor gaps
  3 = Basic reasoning, somewhat generic
  2 = Vague reasoning
  1 = No meaningful reasoning
""",
        "results": results
    }

    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print("\n" + "=" * 60)
    print("EVALUATION COMPLETE")
    print("=" * 60)
    print(f"Total queries     : {len(TEST_QUERIES)}")
    print(f"Successful        : {len(successful)}")
    print(f"Failed            : {len(TEST_QUERIES) - len(successful)}")
    print(f"Avg response time : {avg_time}s")
    print(f"Min response time : {min(response_times)}s")
    print(f"Max response time : {max(response_times)}s")
    print(f"\nSaved to: {OUTPUT}")
    print("Next: fill manual_scores in JSON then run analysis notebook")


if __name__ == "__main__":
    run_evaluation()