def classify_intent(message: str) -> str:
    """Route predictable personal-data questions to deterministic SQL."""
    text = re.sub(r"\s+", " ", message.lower().strip())
    text = re.sub(r"[’']", "'", text)

    recent_meal_terms = (
        "meal", "meals", "food", "foods", "ate", "eaten",
    )
    recent_time_terms = (
        "recent", "latest", "logged", "history",
    )

    if (
        any(term in text for term in recent_meal_terms)
        and any(term in text for term in recent_time_terms)
    ):
        return "recent_meals"

    # Weekly budget and recorded spending.
    budget_terms = (
        "budget", "spending", "spent", "expense", "expenses",
    )
    weekly_terms = (
        "week", "weekly", "this week", "remaining",
    )

    if (
        any(term in text for term in budget_terms)
        and any(term in text for term in weekly_terms)
    ):
        return "weekly_budget"

    # Weekly protein intake.
    protein_terms = ("protein", "proteins")
    weekly_period_terms = (
        "week", "weekly", "this week",
    )

    if (
        any(term in text for term in protein_terms)
        and any(term in text for term in weekly_period_terms)
    ):
        return "weekly_protein"

    daily_nutrition_phrases = (
        "calories today",
        "today's calories",
        "calories have i eaten",
        "calories did i eat",
        "how many calories have i had today",
        "how many calories did i consume today",
        "protein today",
        "protein have i eaten",
        "protein did i eat",
        "how much protein have i had today",
        "how much protein did i consume today",
    )

    if any(phrase in text for phrase in daily_nutrition_phrases):
        return "daily_nutrition"

    return "llm"

def get_direct_answer(intent: str, db: Session, user_id):
    """Answer supported nutrition questions directly from the database."""


    if intent in ("weekly_budget", "weekly_protein"):
        # Define the current Monday-to-Monday week in India time.
        now = datetime.now(IST)
        monday = now.date() - timedelta(days=now.weekday())

        start_ist = datetime.combine(monday, time.min, tzinfo=IST)
        end_ist = start_ist + timedelta(days=7)

        start_utc = start_ist.astimezone(timezone.utc)
        end_utc = end_ist.astimezone(timezone.utc)

        profile = (
            db.query(HealthProfile)
            .filter(HealthProfile.user_id == user_id)
            .first()
        )

        # Let the existing profile-required check handle this case.
        if profile is None:
            return None

        totals = (
            db.query(
                func.coalesce(func.sum(MealLog.cost), 0).label("spent"),
                func.coalesce(func.sum(MealLog.protein_g), 0).label("protein"),
                func.count(MealLog.id).label("meal_count"),
            )
            .filter(
                MealLog.user_id == user_id,
                MealLog.consumed_at >= start_utc,
                MealLog.consumed_at < end_utc,
            )
            .one()
        )

        spent = float(totals.spent or 0)
        protein = float(totals.protein or 0)
        meal_count = int(totals.meal_count or 0)

        week_label = (
            f"{start_ist.strftime('%d %b %Y')} to "
            f"{(end_ist - timedelta(days=1)).strftime('%d %b %Y')}"
        )

        if intent == "weekly_budget":
            weekly_budget = float(profile.daily_budget) * 7
            remaining = weekly_budget - spent

            answer = (
                f"Your configured daily budget is "
                f"{float(profile.daily_budget):,.2f}, giving you a "
                f"weekly budget of {weekly_budget:,.2f} for "
                f"{week_label}.\n\n"
                f"Based on {meal_count} logged meal(s), your recorded "
                f"spending is {spent:,.2f}. Your estimated remaining "
                f"budget is {remaining:,.2f}."
            )

            if meal_count == 0:
                answer += (
                    "\n\nNo meals are recorded for this week, so the "
                    "remaining amount assumes no spending beyond "
                    "what has been logged."
                )
            else:
                answer += (
                    "\n\nThis estimate includes only costs recorded "
                    "against your logged meals. It may not include "
                    "other expenses or unlogged meals."
                )

        else:
            target = profile.daily_protein_target_g

            answer = (
                f"From {meal_count} logged meal(s) between "
                f"{week_label}, your recorded protein intake is "
                f"{protein:.1f} g."
            )

            if target is not None:
                weekly_target = float(target) * 7
                difference = protein - weekly_target

                answer += (
                    f"\n\nYour configured daily protein target is "
                    f"{float(target):.1f} g, equivalent to "
                    f"{weekly_target:.1f} g per week. "
                )

                if difference >= 0:
                    answer += (
                        f"You are {difference:.1f} g above that "
                        f"weekly target based on logged meals."
                    )
                else:
                    answer += (
                        f"You are {abs(difference):.1f} g below that "
                        f"weekly target based on logged meals."
                    )
            else:
                answer += (
                    "\n\nYou haven't configured a daily protein "
                    "target, so I can't compare this total with "
                    "your personal target."
                )

            answer += (
                "\n\nThese figures cover logged meals only and may "
                "underestimate your actual intake."
            )

        return {
            "answer": answer,
            "model": "sql",
            "meals_considered": meal_count,
        }

    if intent == "recent_meals":
        meals = (
            db.query(MealLog)
            .filter(MealLog.user_id == user_id)
            .order_by(MealLog.consumed_at.desc())
            .limit(5)
            .all()
        )

        if not meals:
            return {
                "answer": "You have no logged meals yet.",
                "model": "sql",
                "meals_considered": 0,
            }

        lines = []

        for meal in meals:
            calories = (
                f"{number(meal.calories):.0f}"
                if meal.calories is not None
                else "unknown"
            )

            consumed_at = (
                meal.consumed_at.isoformat()
                if meal.consumed_at is not None
                else "time not recorded"
            )

            lines.append(
                f"- {meal.food_name} ({meal.meal_type}), "
                f"portion: {meal.portion or 'not recorded'}, "
                f"calories: {calories}, "
                f"logged at: {consumed_at}"
            )

        return {
            "answer": (
                "Here are your five most recent logged meals:\n"
                + "\n".join(lines)
            ),
            "model": "sql",
            "meals_considered": len(meals),
        }

    if intent == "daily_nutrition":
        # Define today's calendar day in India Standard Time.
        now = datetime.now(IST)
        start_ist = datetime.combine(
            now.date(),
            time.min,
            tzinfo=IST,
        )
        end_ist = start_ist + timedelta(days=1)

        # The database column is PostgreSQL TIMESTAMPTZ.
        # Keep these datetime objects timezone-aware.
        start_utc = start_ist.astimezone(timezone.utc)
        end_utc = end_ist.astimezone(timezone.utc)

        totals = (
            db.query(
                func.sum(MealLog.calories).label("calories"),
                func.sum(MealLog.protein_g).label("protein"),
                func.count(MealLog.id).label("meal_count"),
            )
            .filter(
                MealLog.user_id == user_id,
                MealLog.consumed_at >= start_utc,
                MealLog.consumed_at < end_utc,
            )
            .one()
        )

        calories = float(totals.calories or 0)
        protein = float(totals.protein or 0)
        meal_count = int(totals.meal_count or 0)

        if meal_count == 0:
            answer = (
                "You haven't logged any meals today, so I can't calculate "
                "your intake yet. Log your meals to see your daily totals."
            )
        else:
            answer = (
                f"Based on {meal_count} logged meal(s) today, your recorded "
                f"intake is approximately {calories:.0f} calories and "
                f"{protein:.1f} g of protein. These totals may be incomplete "
                "if you haven't logged everything you ate."
            )

        return {
            "answer": answer,
            "model": "sql",
            "meals_considered": meal_count,
        }

    return None
