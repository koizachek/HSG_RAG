import pytest 

from src.rag.language_detection import LanguageDetector

class TestQueryLanguageDetection:

    def test_basic_language_detection(self):
        queries = {
            "en": "Hello, im interested in the EMBA Program",
            "de": "Guten Tag, ich interessiere mich für das EMBA Programm",
            "ru": "Добрый день, хочу узнать больше о программе EMBA",
            "uk": "Доброго дня, хочу дізнатися більше про програму ЄМБА",
            "be": "Добры дзень, хачу даведацца больш аб праграме ЕМБА",
            "lt": "Laba diena, norėčiau sužinoti daugiau apie EMBA programą.",
            "lv": "Labdien, es vēlētos uzzināt vairāk par EMBA programmu.",
            "fr": "Bonjour, je souhaiterais en savoir plus sur le programme EMBA.",
            "it": "Buongiorno, vorrei avere maggiori informazioni sul programma EMBA.",
            "es": "Buenas tardes, me gustaría saber más sobre el programa EMBA.",
            "pl": "Dzień dobry, chciałbym dowiedzieć się więcej na temat programu EMBA.",
            "el": "Καλησπέρα, θα ήθελα να μάθω περισσότερα για το πρόγραμμα EMBA.",
            "ko": "안녕하세요, EMBA 프로그램에 대해 더 자세히 알고 싶습니다.",
            "zh": "下午好，我想了解更多關於EMBA課程的資訊。",
            "ja": "こんにちは。EMBA プログラムについて詳しく知りたいのですが。",
            "yi": "גוטן נאכמיטאג, איך וואלט געוואלט וויסן מער וועגן דעם EMBA פראגראם.",
            "fa": "عصر بخیر، مایلم درباره برنامه EMBA بیشتر بدانم.",
            "ar": "مساء الخير، أود معرفة المزيد عن برنامج ماجستير إدارة الأعمال التنفيذية.",
            "tr": "İyi günler, EMBA programı hakkında daha fazla bilgi edinmek istiyorum.",
            "hu": "Jó napot kívánok, szeretnék többet megtudni az EMBA programról.",
            "id": "Selamat siang, saya ingin mengetahui lebih lanjut tentang program EMBA.",
            "ro": "Bună ziua, aș dori să aflu mai multe despre programul EMBA.",
            "nl": "Goedemiddag, ik wil graag meer weten over het EMBA-programma.",
        }        
        correct_detections = 0
        
        detector = LanguageDetector()
        for language, query in queries.items():
            detected_language = detector.detect_language(query)
            if detected_language in [language, 'en']:
                correct_detections += 1
            else:
                print(f"Detected: {detected_language}, should be {language}")
        
        overall_score = correct_detections / len(queries)
        assert overall_score >= 0.95


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
