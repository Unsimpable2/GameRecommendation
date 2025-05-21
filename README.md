Projekt będzie polegac na proponowaniu gier użytkownikowi na bazie opisu czego użytkownik szuka lub wymaga od gry.
Projekt ma w założeniu wykorzystac AI i ML do inteligentego oraz dokładnego polecania gier będących dostępnych na Steam do których można się dostać za pomocą SteamApi.

Zalecany Python do używania to wersja 3.10-3.11.
Używając komendy "pip install -r requirements.txt" zainstaluje wszystko poptrzebne biblioteki.
Do aktualizowania listy komponentów jest potrzebne chromium oraz kompatybilny z wersją chromium ChromeDriver. Chromium powinno zostać umieszczone w ścieżce "C:\Program Files (x86)\Chromium" a ChromeDriver w folderze GameRecommendation.

Do rekomendowania gier i wyciąganiu z promptu użytkownika istotnych informacji używany jest model LLM "Ollama" z modułem "Mistral". Komenda do uruchomienia Ollamy z tym modułem: "ollama run mistral".
Wymagane jest wcześniejsze pobranie tego modułu używajać tej samej komendy w terminalu.

Schemat Bazy Danych
![Schemat Bazy Danych](Scripts/Database/Schemat%20Bazy%20Danych.svg)
