package com.gradedreader.korean

data class KoreanGrammarMatch(val pattern: String, val meaning: String)

object KoreanGrammarDetector {
    private data class Rule(
        val pattern: String,
        val meaning: String,
        val matches: (String) -> Boolean,
    )

    fun detect(surface: String): List<KoreanGrammarMatch> {
        val normalized = surface.trim().removeSurrounding("\"").removeSurrounding("'")
        if (normalized.isEmpty()) return emptyList()

        val matches = rules.asSequence()
            .filter { rule -> rule.matches(normalized) }
            .map { rule -> KoreanGrammarMatch(rule.pattern, rule.meaning) }
            .distinctBy(KoreanGrammarMatch::pattern)
            .toList()

        return matches.filterNot { match ->
            match.pattern == "-아요/어요" && matches.any { it.pattern == "-았/었어요" }
        }
    }

    private fun endsWith(suffix: String): (String) -> Boolean = { value ->
        value.length > suffix.length && value.endsWith(suffix)
    }

    private fun endsWithAny(vararg suffixes: String): (String) -> Boolean = { value ->
        suffixes.any { suffix -> value.length > suffix.length && value.endsWith(suffix) }
    }

    private fun hasPastPoliteEnding(value: String): Boolean {
        if (!value.endsWith("어요") || value.length < 3) return false
        val finalSyllable = value[value.length - 3]
        val codePoint = finalSyllable.code
        return codePoint in HANGUL_BASE..HANGUL_END && (codePoint - HANGUL_BASE) % JONGSEONG_COUNT == PAST_SS_JONGSEONG
    }

    private val rules = listOf(
        Rule("-았/었어요", "past informal polite", ::hasPastPoliteEnding),
        Rule("-았/었어요", "past informal polite", endsWithAny("았어요", "었어요", "였어요", "했어요")),
        Rule("-겠어요", "future or intention (informal polite)", endsWith("겠어요")),
        Rule("-(으)ㄹ 거예요", "future plan or prediction", endsWithAny("을 거예요", "ㄹ 거예요", "거예요")),
        Rule("-고 있어요", "ongoing action", endsWith("고 있어요")),
        Rule("-아/어 보다", "try doing", endsWithAny("아 봐요", "어 봐요", "해 봐요", "아보다", "어보다", "해보다")),
        Rule("-아/어 주다", "do something for someone", endsWithAny("아 줘요", "어 줘요", "해 줘요", "아주다", "어주다", "해주다")),
        Rule("-아/어야 하다", "must; have to", endsWithAny("아야 해요", "어야 해요", "해야 해요", "아야 합니다", "어야 합니다", "해야 합니다")),
        Rule("-(으)면", "if or when", endsWithAny("으면", "면")),
        Rule("-지만", "but; although", endsWith("지만")),
        Rule("-(으)니까", "because; since", endsWithAny("으니까", "니까")),
        Rule("-기 때문에", "because", endsWith("기 때문에")),
        Rule("-아/어서", "because; and then", endsWithAny("아서", "어서", "해서")),
        Rule("-는데", "background or contrast", endsWithAny("는데", "은데", "ㄴ데")),
        Rule("-(으)려고", "in order to; intending to", endsWithAny("으려고", "려고")),
        Rule("-기 위해(서)", "in order to", endsWithAny("기 위해", "기 위해서")),
        Rule("-(으)ㄹ 수 있다/없다", "can or cannot", endsWithAny("을 수 있어요", "ㄹ 수 있어요", "을 수 없어요", "ㄹ 수 없어요", "을 수 있다", "ㄹ 수 있다", "을 수 없다", "ㄹ 수 없다")),
        Rule("-고 싶다", "want to", endsWithAny("고 싶어요", "고 싶다")),
        Rule("-(으)ㄹ까요?", "shall we; shall I; guess", endsWithAny("을까요", "ㄹ까요")),
        Rule("-(으)세요", "polite request or command", endsWithAny("으세요", "세요")),
        Rule("-지 마세요", "please do not", endsWith("지 마세요")),
        Rule("-아/어 주세요", "please do", endsWithAny("아 주세요", "어 주세요", "해 주세요")),
        Rule("-지 않다", "not; negation", endsWithAny("지 않아요", "지 않습니다", "지 않았다", "지 않다")),
        Rule("-지 못하다", "cannot; inability", endsWithAny("지 못해요", "지 못합니다", "지 못하다")),
        Rule("-고", "and; then", endsWith("고")),
        Rule("-아/어", "connective ending", endsWithAny("아", "어", "해")),
        Rule("-(으)ㄴ/는", "modifier ending", endsWithAny("은", "는", "ㄴ")),
        Rule("-(으)ㄹ", "future modifier ending", endsWithAny("을", "ㄹ")),
        Rule("-아요/어요", "informal polite present", endsWithAny("아요", "어요", "해요")),
        Rule("-습니다/ㅂ니다", "formal polite statement", endsWithAny("습니다", "ㅂ니다")),
        Rule("-습니까?", "formal polite question", endsWith("습니까")),
        Rule("-이에요/예요", "copula: is", endsWithAny("이에요", "예요")),
        Rule("-이/가", "subject particle", endsWithAny("이", "가")),
        Rule("-을/를", "object particle", endsWithAny("을", "를")),
        Rule("-은/는", "topic particle", endsWithAny("은", "는")),
        Rule("-에", "place or time particle", endsWith("에")),
        Rule("-에서", "location of an action", endsWith("에서")),
        Rule("-에게/한테", "to a person", endsWithAny("에게", "한테")),
        Rule("-와/과", "and; with", endsWithAny("와", "과")),
        Rule("-도", "also; too", endsWith("도")),
        Rule("-부터/까지", "from; until", endsWithAny("부터", "까지")),
    )

    private const val HANGUL_BASE = 0xAC00
    private const val HANGUL_END = 0xD7A3
    private const val JONGSEONG_COUNT = 28
    private const val PAST_SS_JONGSEONG = 20
}
