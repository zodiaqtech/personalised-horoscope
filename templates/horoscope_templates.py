"""
Static text templates for horoscope rendering.
Scores are converted to bands, bands mapped to pre-written sentences.

Band mapping:
  4 to 5    → very_positive
  2 to 3    → favourable
  0 to 1    → neutral
 -1 to -2   → caution
 -3 to -5   → challenging
"""
from typing import Dict


# ─────────────────────────────────────────────
# Score → Band
# ─────────────────────────────────────────────

def score_to_band(score: float) -> str:
    if score >= 4:
        return "very_positive"
    elif score >= 2:
        return "favourable"
    elif score >= 0:
        return "neutral"
    elif score >= -2:
        return "caution"
    else:
        return "challenging"


# ─────────────────────────────────────────────
# Templates: area → band → text
# ─────────────────────────────────────────────

TEMPLATES: Dict[str, Dict[str, str]] = {

    "career": {
        "very_positive": (
            "Career energies are exceptionally strong today. "
            "Bold initiatives and important professional decisions receive strong planetary support. "
            "Superiors are likely to take notice of your efforts — this is an auspicious day to make your mark."
        ),
        "favourable": (
            "Professional activities receive structured support today. "
            "Efforts made are likely to yield tangible progress. "
            "A good day to push forward on pending tasks, follow up with contacts, or present ideas."
        ),
        "neutral": (
            "Career matters proceed at a steady, unremarkable pace today. "
            "Focus on routine responsibilities and planning. "
            "No major breakthroughs are indicated, but consistent work will serve you well."
        ),
        "caution": (
            "Exercise care in professional decisions today. "
            "Avoid impulsive moves, conflicts with authority, or signing important agreements. "
            "Patience and careful observation will be more rewarding than aggressive action."
        ),
        "challenging": (
            "Career fronts may face resistance today. "
            "Pause major decisions and focus on consolidation. "
            "Misunderstandings are possible — choose communication carefully and avoid confrontation."
        ),
    },

    "finance": {
        "very_positive": (
            "Financial prospects are highly auspicious today. "
            "Gains, inflows, and opportunities to increase wealth are strongly supported by planetary positions. "
            "Consider making informed investments or settling pending financial matters."
        ),
        "favourable": (
            "A positive day for financial matters. "
            "Moderate gains and steady inflows are indicated. "
            "Good for managing expenses, receiving dues, or initiating financial plans."
        ),
        "neutral": (
            "Financial energies are balanced today — neither strong gains nor significant losses are indicated. "
            "Maintain existing plans and avoid impulsive expenditures. "
            "A good day for budgeting and reviewing financial standing."
        ),
        "caution": (
            "Exercise caution with money today. "
            "Avoid large purchases, speculative ventures, or lending without documentation. "
            "Unexpected expenses may arise — keep a financial buffer handy."
        ),
        "challenging": (
            "Financial matters require careful attention today. "
            "Planetary positions indicate possible strain — avoid risky investments or unnecessary expenditure. "
            "Focus on protecting existing assets rather than seeking new gains."
        ),
    },

    "love": {
        "very_positive": (
            "Love and relationships are beautifully supported today. "
            "Romantic connections deepen, meaningful conversations flow naturally, "
            "and opportunities to strengthen bonds are abundant. "
            "An excellent day for important conversations or expressing feelings."
        ),
        "favourable": (
            "Relationships carry a warm and harmonious tone today. "
            "Small gestures of affection and honest communication will go a long way. "
            "A good day for spending quality time with those you care about."
        ),
        "neutral": (
            "Relationships proceed without major turbulence or excitement today. "
            "Maintain steady communication and be present with loved ones. "
            "Nothing extraordinary is indicated, but connection and routine warmth matter."
        ),
        "caution": (
            "Handle relationships with sensitivity today. "
            "Misunderstandings or emotional friction may surface — choose words thoughtfully. "
            "Avoid making assumptions and give loved ones the benefit of the doubt."
        ),
        "challenging": (
            "Relationships may feel strained or tense today. "
            "Planetary influences suggest emotional turbulence or conflict risks. "
            "Give space where needed, avoid escalating arguments, and prioritise inner calm."
        ),
    },

    "health": {
        "very_positive": (
            "Vitality and physical well-being are strongly supported today. "
            "Energy levels are high and the body responds well to positive habits. "
            "A good day for starting a new health routine or physical activity."
        ),
        "favourable": (
            "Health energies are positive today. "
            "Moderate activity, healthy eating, and rest will reinforce your well-being. "
            "A good day for medical consultations or addressing minor health concerns."
        ),
        "neutral": (
            "Health remains stable and unremarkable today. "
            "Maintain your usual routines, stay hydrated, and get adequate rest. "
            "No special vigilance is required."
        ),
        "caution": (
            "Be mindful of your health today. "
            "Planetary positions suggest possible fatigue, minor ailments, or digestive discomfort. "
            "Avoid overexertion, eat light, and get sufficient rest."
        ),
        "challenging": (
            "Health requires careful attention today. "
            "Planetary positions indicate potential vulnerability — avoid risky activities "
            "and listen to your body's signals. Consult a professional for any persisting concerns."
        ),
    },

    "mental": {
        "very_positive": (
            "Mental clarity and emotional equilibrium are at their peak today. "
            "Complex thinking, creative problem-solving, and emotional intelligence are all well-supported. "
            "An excellent day for study, strategy, or any work requiring sharp focus."
        ),
        "favourable": (
            "Mental energy is clear and productive today. "
            "Focus comes naturally and decision-making is sound. "
            "A good day for intellectually demanding tasks or learning something new."
        ),
        "neutral": (
            "Mental state is balanced and calm today. "
            "Neither exceptional clarity nor significant fog is indicated. "
            "Routine cognitive tasks and steady thinking will serve you well."
        ),
        "caution": (
            "Mental energies may feel scattered or restless today. "
            "Avoid overloading your schedule or making decisions under stress. "
            "Short breaks, mindfulness, and reducing distractions will help."
        ),
        "challenging": (
            "Mental and emotional well-being may feel strained today. "
            "Anxiety, overthinking, or low motivation are possible. "
            "Prioritise rest, avoid unnecessary conflict, and seek grounding through simple routines."
        ),
    },

    "spiritual": {
        "very_positive": (
            "Spiritual energies are remarkably elevated today. "
            "Meditation, prayer, charitable acts, and inner reflection are deeply rewarding now. "
            "A powerful day for spiritual practice or seeking higher guidance."
        ),
        "favourable": (
            "A positive day for spiritual growth and inner reflection. "
            "Quiet contemplation, gratitude practices, or time in nature will feel uplifting. "
            "Good for connecting with your values and sense of purpose."
        ),
        "neutral": (
            "Spiritual energies are calm and steady today. "
            "Maintain your regular practices — meditation, journaling, or time for stillness. "
            "No dramatic shifts, but consistent inner work accumulates meaningfully."
        ),
        "caution": (
            "Spiritual energies may feel dulled or distracted today. "
            "External busyness can crowd out inner reflection — be intentional about carving out quiet time. "
            "Avoid excessive attachment to outcomes."
        ),
        "challenging": (
            "Inner restlessness or spiritual doubt may surface today. "
            "Planetary positions suggest a testing phase for the inner self. "
            "Lean into compassion and patience with yourself — difficult phases are also teachers."
        ),
    },
}

# ─────────────────────────────────────────────
# Overall summary templates (derived from average band)
# ─────────────────────────────────────────────

OVERALL_TEMPLATES: Dict[str, str] = {
    "very_positive": (
        "Today is exceptionally auspicious across most life areas. "
        "Planetary alignments strongly favour action, growth, and meaningful connection. "
        "Make the most of this high-energy day."
    ),
    "favourable": (
        "Overall, today carries positive and supportive energies. "
        "Most areas of life benefit from steady effort and thoughtful action. "
        "A good day to make progress on important matters."
    ),
    "neutral": (
        "Today is a balanced, moderate day. "
        "Life proceeds steadily — no exceptional highs or lows are indicated. "
        "Focus on consistency, self-care, and measured progress."
    ),
    "caution": (
        "Today calls for mindfulness and restraint. "
        "Planetary influences suggest some friction in key areas — "
        "approach decisions carefully and avoid unnecessary risks."
    ),
    "challenging": (
        "Today presents some planetary challenges. "
        "Patience, inner resilience, and careful action will help you navigate the day. "
        "Focus on what you can control and avoid forcing outcomes."
    ),
}


# ─────────────────────────────────────────────
# Nakshatra lord daily tone — per life area (Phase 4+)
# ─────────────────────────────────────────────
# Each life area (career, finance, love, health, mental, spiritual) plus
# "overall" has its own list of 9 lord-group sentences.
# Indexed by nakshatra_idx % 9 (lord group: 0=Ketu, 1=Venus, 2=Sun,
# 3=Moon, 4=Mars, 5=Rahu, 6=Jupiter, 7=Saturn, 8=Mercury).
# Moon changes nakshatra every ~1 day → each area's appended sentence
# varies daily, even when no planet changes zodiac sign overnight.

NAKSHATRA_AREA_DAILY_TONE_EN: Dict[str, list] = {

    "overall": [
        # 0 — Ketu
        "Ketu's lunar energy invites release and inner purification today — "
        "letting go of what no longer serves will create space for renewal.",
        # 1 — Venus
        "Venus's nakshatra lends a creative and aesthetic quality to the day — "
        "beauty, pleasure, and artistic expression are especially favoured.",
        # 2 — Sun
        "The Sun's nakshatra lends authority and clarity today — "
        "actions taken with purpose and integrity can yield lasting results.",
        # 3 — Moon
        "The Moon's own nakshatra heightens emotional intelligence and receptivity — "
        "nurturing, deep listening, and genuine care are especially rewarded today.",
        # 4 — Mars
        "Mars's nakshatra energises initiative and creative dynamism — "
        "bold, well-directed action is strongly supported by today's lunar energy.",
        # 5 — Rahu
        "Rahu's nakshatra favours unconventional thinking and transformation today — "
        "embrace change and be open to exploring new, unexpected approaches.",
        # 6 — Jupiter
        "Jupiter's nakshatra expands vision and wisdom today — "
        "long-term thinking, learning, and growth-oriented action are strongly favoured.",
        # 7 — Saturn
        "Saturn's nakshatra rewards disciplined, patient effort and loyal commitment — "
        "steady perseverance and methodical work yield the most lasting gains today.",
        # 8 — Mercury
        "Mercury's nakshatra sharpens communication and analytical thinking today — "
        "clarity in expression, thoughtful dialogue, and careful analysis are especially rewarded.",
    ],

    "career": [
        # 0 — Ketu
        "Ketu's energy calls for stepping back from ego-driven ambition today — "
        "release attachment to outcomes and focus on purposeful, dharmic work.",
        # 1 — Venus
        "Venus's nakshatra favours diplomacy, relationship-building, and creative collaboration at work today — "
        "charm and cooperation open professional doors.",
        # 2 — Sun
        "The Sun's nakshatra amplifies leadership and professional authority today — "
        "step forward with confidence and take ownership of your goals.",
        # 3 — Moon
        "The Moon's nakshatra highlights emotional intelligence in professional settings today — "
        "read the room, adapt with care, and lead with empathy.",
        # 4 — Mars
        "Mars's nakshatra drives ambition, initiative, and competitive energy at work today — "
        "bold decisions and decisive actions are well-supported.",
        # 5 — Rahu
        "Rahu's nakshatra favours unconventional career moves and innovation today — "
        "thinking outside the box can unlock unexpected professional opportunities.",
        # 6 — Jupiter
        "Jupiter's nakshatra broadens professional vision and favours mentorship, teaching, and strategic growth today — "
        "think long-term in career matters.",
        # 7 — Saturn
        "Saturn's nakshatra rewards disciplined effort, reliability, and structured work today — "
        "steady, committed action builds lasting professional reputation.",
        # 8 — Mercury
        "Mercury's nakshatra sharpens professional communication and analytical ability today — "
        "negotiations, presentations, and written work are especially favoured.",
    ],

    "finance": [
        # 0 — Ketu
        "Ketu's energy invites detachment from material gain today — "
        "avoid speculative risks and focus on protecting and stewarding existing resources.",
        # 1 — Venus
        "Venus's nakshatra favours financial gains through creative, artistic, or luxury-related ventures today — "
        "aesthetic value can translate into monetary gain.",
        # 2 — Sun
        "The Sun's nakshatra supports transactions requiring authority and clarity today — "
        "government dealings, official financial matters, and strategic investments benefit.",
        # 3 — Moon
        "The Moon's nakshatra highlights emotional spending patterns today — "
        "nurture financial security by being mindful of comfort-driven purchases.",
        # 4 — Mars
        "Mars's nakshatra energises decisive financial action today — "
        "bold investment moves are supported, but guard against impulsiveness.",
        # 5 — Rahu
        "Rahu's nakshatra favours unconventional financial opportunities today — "
        "new-age investments or emerging avenues may yield gains, but research thoroughly first.",
        # 6 — Jupiter
        "Jupiter's nakshatra expands wealth consciousness today — "
        "long-term financial planning, ethical investments, and charitable giving are strongly favoured.",
        # 7 — Saturn
        "Saturn's nakshatra rewards frugality, patience, and methodical financial management today — "
        "slow and steady accumulation outpaces risky shortcuts.",
        # 8 — Mercury
        "Mercury's nakshatra sharpens financial analysis and negotiation today — "
        "carefully read contracts, review accounts, and seek clarity before committing funds.",
    ],

    "love": [
        # 0 — Ketu
        "Ketu's energy invites emotional release and spiritual bonding in relationships today — "
        "deep, soulful connection matters more than surface pleasantries.",
        # 1 — Venus
        "Venus's nakshatra beautifully supports romance, affection, and aesthetic experiences shared with loved ones today — "
        "an excellent day for tender connection.",
        # 2 — Sun
        "The Sun's nakshatra brings clarity and honesty to relationships today — "
        "authentic expression of feelings and a confident, warm presence strengthen bonds.",
        # 3 — Moon
        "The Moon's own nakshatra heightens emotional depth and nurturing in relationships today — "
        "deep listening and sincere care bring loved ones closer.",
        # 4 — Mars
        "Mars's nakshatra adds passion and intensity to romantic connections today — "
        "feelings are strong; channel energy into loving action rather than conflict.",
        # 5 — Rahu
        "Rahu's nakshatra opens relationships to exciting, unconventional experiences today — "
        "try something new together and embrace the unexpected.",
        # 6 — Jupiter
        "Jupiter's nakshatra expands love through wisdom and shared values today — "
        "meaningful conversations, spiritual connection, and growth together are favoured.",
        # 7 — Saturn
        "Saturn's nakshatra rewards loyal, committed, and enduring bonds today — "
        "slow-burning, steadfast love proves more fulfilling than fleeting excitement.",
        # 8 — Mercury
        "Mercury's nakshatra favours witty, intellectually stimulating exchanges in relationships today — "
        "conversation, humour, and shared ideas deepen connection.",
    ],

    "health": [
        # 0 — Ketu
        "Ketu's energy invites subtle body awareness today — "
        "intuitive healing, rest, and releasing tension from the body are especially beneficial.",
        # 1 — Venus
        "Venus's nakshatra favours pleasurable, restorative health practices today — "
        "gentle exercise, nourishing food, and beauty-enhancing routines support well-being.",
        # 2 — Sun
        "The Sun's nakshatra bolsters vitality and immune strength today — "
        "spend time in sunlight, maintain an active routine, and prioritise energy levels.",
        # 3 — Moon
        "The Moon's nakshatra heightens sensitivity in the body today — "
        "stay well-hydrated, eat light, and be attentive to emotional patterns that affect physical health.",
        # 4 — Mars
        "Mars's nakshatra fuels physical energy and stamina today — "
        "vigorous exercise, strength training, and active pursuits are strongly supported.",
        # 5 — Rahu
        "Rahu's nakshatra calls for mindful health choices today — "
        "avoid erratic routines and pay attention to subtle symptoms that may otherwise go unnoticed.",
        # 6 — Jupiter
        "Jupiter's nakshatra supports holistic wellness and preventive health practices today — "
        "integrate healing modalities that address body, mind, and spirit.",
        # 7 — Saturn
        "Saturn's nakshatra rewards consistent, disciplined health habits today — "
        "stick to your routine, prioritise sleep, and avoid shortcuts in self-care.",
        # 8 — Mercury
        "Mercury's nakshatra highlights mind-body awareness today — "
        "breathing exercises, journaling, and addressing mental stressors that impact physical health are beneficial.",
    ],

    "mental": [
        # 0 — Ketu
        "Ketu's energy favours introspection and letting go of mental clutter today — "
        "silence, meditation, and releasing repetitive thoughts renew mental clarity.",
        # 1 — Venus
        "Venus's nakshatra brings creative inspiration and aesthetic joy to mental life today — "
        "artistic pursuits, beautiful environments, and pleasure nourish the mind.",
        # 2 — Sun
        "The Sun's nakshatra sharpens mental focus and willpower today — "
        "clarity of purpose fuels concentration; trust your insight and act decisively.",
        # 3 — Moon
        "The Moon's nakshatra deepens emotional awareness and receptive intelligence today — "
        "creative thinking, imagination, and empathic understanding are at their peak.",
        # 4 — Mars
        "Mars's nakshatra energises mental drive and competitive thinking today — "
        "tackle challenging problems head-on and channel mental fire into productive output.",
        # 5 — Rahu
        "Rahu's nakshatra stimulates unconventional thinking and mental exploration today — "
        "creative breakthroughs come from questioning assumptions and embracing novel ideas.",
        # 6 — Jupiter
        "Jupiter's nakshatra expands the mind through wisdom and philosophical inquiry today — "
        "reading, learning, and big-picture thinking are richly rewarding.",
        # 7 — Saturn
        "Saturn's nakshatra supports concentrated, methodical mental effort today — "
        "deep work, structured study, and sustained focus yield the most valuable results.",
        # 8 — Mercury
        "Mercury's nakshatra is at its most potent today — "
        "communication, logical analysis, writing, and linguistic skill are exceptionally sharp and well-supported.",
    ],

    "spiritual": [
        # 0 — Ketu
        "Ketu's nakshatra makes this a deeply auspicious day for moksha-oriented practice — "
        "detachment, surrender, and silent meditation align you with the infinite.",
        # 1 — Venus
        "Venus's nakshatra invites devotional beauty into spiritual life today — "
        "sacred music, artistic offerings, and bhakti practices carry a special luminosity.",
        # 2 — Sun
        "The Sun's nakshatra connects spiritual practice to dharma and self-luminosity today — "
        "meditation on one's true purpose and sincere tapas bring deep inner rewards.",
        # 3 — Moon
        "The Moon's nakshatra fills spiritual practice with deep compassion and devotion today — "
        "heart-centred prayer, mantra chanting, and selfless service are especially fruitful.",
        # 4 — Mars
        "Mars's nakshatra energises the spiritual will today — "
        "disciplined sadhana, courageous inner inquiry, and breaking through spiritual stagnation are strongly favoured.",
        # 5 — Rahu
        "Rahu's nakshatra opens the door to transformative spiritual experiences today — "
        "unconventional wisdom paths, shadow work, and embracing the unknown deepen the journey.",
        # 6 — Jupiter
        "Jupiter's nakshatra makes this an excellent day for scriptural study, satsang, and learning from a guru — "
        "wisdom received now resonates deeply.",
        # 7 — Saturn
        "Saturn's nakshatra rewards patient, persistent spiritual practice today — "
        "consistency in routine, humility, and service-oriented devotion build lasting inner strength.",
        # 8 — Mercury
        "Mercury's nakshatra sharpens mantra recitation, sacred study, and contemplative dialogue today — "
        "the spoken and written word carries spiritual power.",
    ],
}


def get_moon_nakshatra_tone(nakshatra_idx: int, lang: str = "en", area: str = "overall") -> str:
    """
    Return the daily nakshatra lord tone sentence for today's Moon position.

    Args:
        nakshatra_idx: Moon's nakshatra index (0-26), from get_today_moon_nakshatra()
        lang: "en" or "hi"
        area: Life area key — "career", "finance", "love", "health", "mental",
              "spiritual", or "overall" (default)
    """
    lord_group = nakshatra_idx % 9
    if lang == "hi":
        from templates.horoscope_templates_hi import NAKSHATRA_AREA_DAILY_TONE_HI
        area_tones = NAKSHATRA_AREA_DAILY_TONE_HI.get(area, NAKSHATRA_AREA_DAILY_TONE_HI["overall"])
        return area_tones[lord_group]
    area_tones = NAKSHATRA_AREA_DAILY_TONE_EN.get(area, NAKSHATRA_AREA_DAILY_TONE_EN["overall"])
    return area_tones[lord_group]


def get_template(area: str, band: str, lang: str = "en") -> str:
    """Return the pre-written text for a given life area and band.

    Args:
        area: Life area key (career, finance, love, health, mental, spiritual)
        band: Score band (very_positive, favourable, neutral, caution, challenging)
        lang: Language code — "en" (default) or "hi"
    """
    if lang == "hi":
        from templates.horoscope_templates_hi import get_template_hi
        return get_template_hi(area, band)
    area_templates = TEMPLATES.get(area, {})
    return area_templates.get(band, "Today brings a mix of energies in this area. Proceed with awareness.")


def get_overall_template(average_score: float, lang: str = "en") -> str:
    """Return the overall summary text based on average score across all areas.

    Args:
        average_score: Mean clamped score across all life areas
        lang: Language code — "en" (default) or "hi"
    """
    if lang == "hi":
        from templates.horoscope_templates_hi import get_overall_template_hi
        return get_overall_template_hi(average_score)
    band = score_to_band(average_score)
    return OVERALL_TEMPLATES.get(band, "Today unfolds with a balance of planetary energies.")
