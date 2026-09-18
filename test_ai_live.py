import requests
import json
import assistant_engine

print("در حال ارسال سوال به مدل هوش مصنوعی محلی...")
result = assistant_engine.process_assistant_message("امروز کدو مشتری رو تسویه کنم ؟")
print("\n✦ پاسخ هوش مصنوعی:")
print(result.get("answer"))
