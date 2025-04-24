import json
import os

# פונקציה למציאת המשפט הארוך ביותר ב-sentence וב-translation
def find_longest_sentences(data):
    longest_sentence = {"text": "", "word_count": 0}
    longest_translation = {"text": "", "word_count": 0}

    # מעבר רק על דוגמאות בתת נושאים
    for level in data["levels"]:
        for subtopic in level["subtopics"]:
            for word in subtopic["words"]:
                for example in word["examples"]:
                    sentence = example["sentence"]
                    translation = example["translation"]
                    
                    # חישוב מספר המילים
                    sentence_word_count = len(sentence.split())
                    translation_word_count = len(translation.split())
                    
                    # בדיקה עבור sentence
                    if sentence_word_count > longest_sentence["word_count"]:
                        longest_sentence["text"] = sentence
                        longest_sentence["word_count"] = sentence_word_count
                    
                    # בדיקה עבור translation
                    if translation_word_count > longest_translation["word_count"]:
                        longest_translation["text"] = translation
                        longest_translation["word_count"] = translation_word_count

    return longest_sentence, longest_translation

# משתנים לאחסון המשפטים הארוכים ביותר שנמצאו מכל הקבצים
longest_sentence_overall = {"text": "", "word_count": 0}
longest_translation_overall = {"text": "", "word_count": 0}

# מעבר על כל הקבצים מ-4 עד 10
for i in range(4, 11):
    filename = f"words_level_{i}.json"
    
    # בדיקה אם הקובץ קיים בתיקייה
    if os.path.exists(filename):
        with open(filename, "r", encoding="utf-8") as file:
            data = json.load(file)
        
        # חיפוש המשפטים הארוכים ביותר בקובץ הנוכחי
        longest_sentence, longest_translation = find_longest_sentences(data)
        
        # הצגת התוצאה עבור הקובץ הנוכחי
        print(f"Results for {filename}:")
        print("  Longest sentence:", longest_sentence["text"])
        print("  Word count of longest sentence:", longest_sentence["word_count"])
        print("  Longest translation:", longest_translation["text"])
        print("  Word count of longest translation:", longest_translation["word_count"])
        print("-" * 40)  # קו מפריד בין התוצאות

        # עדכון המשפטים הארוכים ביותר מכלל הקבצים
        if longest_sentence["word_count"] > longest_sentence_overall["word_count"]:
            longest_sentence_overall = longest_sentence
        if longest_translation["word_count"] > longest_translation_overall["word_count"]:
            longest_translation_overall = longest_translation

# הצגת התוצאות הכוללות מכלל הקבצים
print("Overall longest sentence across all files:")
print("  Text:", longest_sentence_overall["text"])
print("  Word count:", longest_sentence_overall["word_count"])

print("Overall longest translation across all files:")
print("  Text:", longest_translation_overall["text"])
print("  Word count:", longest_translation_overall["word_count"])
