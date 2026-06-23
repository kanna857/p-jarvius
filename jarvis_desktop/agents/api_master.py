import requests
import subprocess
import os
import imaplib
import email
from email.header import decode_header
from pathlib import Path
from utils.logger import JarvisLogger
from utils.cache import cached

class APIMaster:
    def __init__(self, config):
        self.config = config
        self.logger = JarvisLogger("APIMaster")

    @cached(ttl=300, key="hyderabad_weather")  # cache 5 minutes
    def get_hyderabad_weather(self) -> str:
        """Instant accurate local weather reading"""
        try:
            self.logger.info("Querying atmospheric data for Hyderabad...")
            
            # Use OpenWeatherMap if key is provided
            if getattr(self.config, 'WEATHER_API_KEY', None):
                url = f"https://api.openweathermap.org/data/2.5/weather?q=Hyderabad&appid={self.config.WEATHER_API_KEY}&units=metric"
                resp = requests.get(url, timeout=5)
                if resp.status_code == 200:
                    d = resp.json()
                    temp = d.get("main", {}).get("temp")
                    desc = d.get("weather", [{}])[0].get("description", "unknown")
                    ws = d.get("wind", {}).get("speed")
                    return f"Current Hyderabad conditions: {temp}°C with {desc}, wind speed {ws} m/s."

            # Fallback to Open-Meteo
            url = "https://api.open-meteo.com/v1/forecast?latitude=17.3850&longitude=78.4867&current_weather=true"
            resp = requests.get(url, timeout=5)
            if resp.status_code == 200:
                d = resp.json().get("current_weather", {})
                temp = d.get("temperature")
                ws = d.get("windspeed")
                return f"Current Hyderabad conditions: {temp}°C, wind speed {ws} km/h. Perfect conditions for operations."
            
            # Fallback text-based
            resp = requests.get("https://wttr.in/Hyderabad?format=3", timeout=5)
            return f"Weather: {resp.text.strip()}"
        except Exception as e:
            self.logger.warning(f"Weather check error: {e}")
            return "Atmospheric sensors failed."

    def get_local_github_diff(self, repo_path: str = None) -> str:
        """Analyzes local repository changes instantaneously"""
        try:
            p = repo_path or os.getcwd()
            self.logger.info(f"Analyzing repo differential at {p}")
            r = subprocess.run(
                ["git", "status", "--short"], 
                cwd=p, 
                capture_output=True, 
                text=True, 
                timeout=5
            )
            changed = r.stdout.strip()
            if not changed:
                return "The current repository status is nominal. No uncommitted changes detected."
            
            files = [line.split()[-1] for line in changed.split("\n")][:5]
            return f"Active development detected in: {', '.join(files)}."
        except Exception as e:
            return "Repository not available or not initialized with Git."

    def _cric(self, endpoint: str, params: dict = None) -> dict | None:
        """Helper: call any cricapi.com v1 endpoint. Returns parsed JSON or None."""
        api_key = getattr(self.config, 'CRICKET_API_KEY', '')
        if not api_key:
            return None
        p = {"apikey": api_key, "offset": 0}
        if params:
            p.update(params)
        try:
            url = f"https://api.cricapi.com/v1/{endpoint}"
            resp = requests.get(url, params=p, timeout=8)
            if resp.status_code == 200:
                return resp.json()
            self.logger.warning(f"CricAPI [{endpoint}] {resp.status_code}: {resp.text[:80]}")
        except Exception as e:
            self.logger.warning(f"CricAPI [{endpoint}] error: {e}")
        return None

    @cached(ttl=60, key="live_cricket")  # cache 1 minute — scores change fast
    def check_live_cricket(self) -> str:
        """Live cricket scores — uses cricScore (fastest) then currentMatches fallback."""
        # Try cricScore first — compact, fast live scorecard
        data = self._cric("cricScore")
        if data and data.get("data"):
            matches = data["data"]
            if not matches:
                return "No live cricket matches right now."
            lines = []
            for m in matches[:5]:
                t1 = m.get("t1", "Team 1")
                t2 = m.get("t2", "Team 2")
                t1s = m.get("t1s", "")
                t2s = m.get("t2s", "")
                status = m.get("ms", "")
                series = m.get("series", "")
                score_line = f"🏏 {t1} vs {t2}"
                if t1s or t2s:
                    score_line += f"\n   {t1}: {t1s}  |  {t2}: {t2s}"
                score_line += f"\n   {status}" + (f" [{series}]" if series else "")
                lines.append(score_line)
            return "Live Cricket Scores:\n\n" + "\n\n".join(lines)

        # Fallback: currentMatches
        data = self._cric("currentMatches")
        if data and data.get("data"):
            matches = data["data"]
            if not matches:
                return "No live cricket matches right now."
            lines = []
            for m in matches[:4]:
                name = m.get("name", "Match")
                status = m.get("status", "")
                score_list = m.get("score", [])
                if score_list:
                    scores = "  |  ".join(
                        f"{s.get('inning','')}: {s.get('r',0)}/{s.get('w',0)} ({s.get('o',0)} ov)"
                        for s in score_list
                    )
                    lines.append(f"🏏 {name}\n   {scores}\n   {status}")
                else:
                    lines.append(f"🏏 {name} — {status}")
            return "Live Cricket Scores:\n\n" + "\n\n".join(lines)

        # Last resort: DuckDuckGo
        try:
            from duckduckgo_search import DDGS
            with DDGS() as ddgs:
                res = list(ddgs.text("live cricket score today", max_results=1))
            if res:
                return f"Cricket Update: {res[0]['body'][:200]}"
        except Exception:
            pass
        return "Cricket scores currently unavailable."

    def get_cricket_matches(self) -> str:
        """Returns list of all upcoming and recent cricket matches."""
        data = self._cric("matches")
        if not data or not data.get("data"):
            return "No cricket match data available."
        matches = data["data"][:8]
        lines = []
        for m in matches:
            name = m.get("name", "Match")
            date = m.get("date", "TBD")
            venue = m.get("venue", "")
            status = m.get("status", "")
            line = f"📅 {name} — {date}"
            if venue:
                line += f" @ {venue}"
            if status:
                line += f" [{status}]"
            lines.append(line)
        return "Cricket Matches:\n" + "\n".join(lines)

    def get_cricket_match_info(self, match_id: str) -> str:
        """Returns detailed info about a specific match by its ID."""
        data = self._cric("match_info", {"id": match_id})
        if not data or not data.get("data"):
            return f"Could not find match info for ID: {match_id}"
        m = data["data"]
        name = m.get("name", "Match")
        date = m.get("date", "")
        venue = m.get("venue", "")
        status = m.get("status", "")
        toss = m.get("tossChoice", "")
        score_list = m.get("score", [])
        lines = [f"🏏 {name}", f"📅 Date: {date}", f"🏟️ Venue: {venue}", f"Status: {status}"]
        if toss:
            lines.append(f"Toss: {toss}")
        for s in score_list:
            lines.append(f"  {s.get('inning','')}: {s.get('r',0)}/{s.get('w',0)} ({s.get('o',0)} ov)")
        return "\n".join(lines)

    def search_cricket_player(self, name: str) -> str:
        """Searches for a cricket player by name."""
        data = self._cric("players", {"search": name})
        if not data or not data.get("data"):
            return f"No players found matching '{name}'."
        players = data["data"][:5]
        lines = []
        for p in players:
            pname = p.get("name", "")
            country = p.get("country", "")
            pid = p.get("id", "")
            lines.append(f"🏏 {pname} ({country}) — ID: {pid}")
        return f"Cricket Players matching '{name}':\n" + "\n".join(lines)

    def get_cricket_player_info(self, player_id: str) -> str:
        """Returns detailed career stats and bio of a cricket player by ID."""
        data = self._cric("players_info", {"id": player_id})
        if not data or not data.get("data"):
            return f"Could not find player info for ID: {player_id}"
        p = data["data"]
        name = p.get("name", "")
        country = p.get("country", "")
        role = p.get("role", "")
        bat = p.get("battingStyle", "")
        bowl = p.get("bowlingStyle", "")
        dob = p.get("dateOfBirth", "")
        desc = p.get("description", "")[:200] if p.get("description") else ""
        lines = [
            f"🏏 {name} ({country})",
            f"Role: {role}",
            f"Batting: {bat}",
            f"Bowling: {bowl}",
            f"Born: {dob}",
        ]
        if desc:
            lines.append(f"About: {desc}...")
        return "\n".join(lines)

    def get_cricket_series_info(self, series_id: str) -> str:
        """Returns info about a cricket series/tournament by ID."""
        data = self._cric("series_info", {"id": series_id})
        if not data or not data.get("data"):
            return f"Could not find series info for ID: {series_id}"
        s = data["data"]
        name = s.get("name", "Series")
        start = s.get("startdate", "")
        end = s.get("enddate", "")
        matches = s.get("matches", [])
        lines = [f"🏆 {name}", f"📅 {start} → {end}", f"Matches: {len(matches)}"]
        for m in matches[:6]:
            lines.append(f"  • {m.get('name','')}")
        return "\n".join(lines)

    def get_cricket_squad(self, match_id: str) -> str:
        """Returns the playing squads for a cricket match by match ID."""
        data = self._cric("match_squad", {"id": match_id})
        if not data or not data.get("data"):
            return f"Could not find squad info for match ID: {match_id}"
        squads = data["data"]
        lines = ["🏏 Match Squads:"]
        for team_data in squads[:2]:
            team = team_data.get("team", {})
            tname = team.get("name", "Team")
            players = team_data.get("players", [])
            lines.append(f"\n{tname}:")
            for pl in players[:11]:
                lines.append(f"  • {pl.get('name','')}")
        return "\n".join(lines)

    @cached(ttl=300, key="top_news")  # cache 5 minutes
    def get_latest_news(self) -> str:
        """Pulls top news headlines using NewsAPI.org"""
        if not getattr(self.config, 'NEWS_API_KEY', None):
            return "News API key is not configured."
        try:
            url = f"https://newsapi.org/v2/top-headlines?country=in&pageSize=5&apiKey={self.config.NEWS_API_KEY}"
            resp = requests.get(url, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                articles = data.get("articles", [])
                if not articles:
                    return "No latest news found right now."
                
                headlines = []
                for idx, article in enumerate(articles[:5]):
                    title = article.get("title", "")
                    source = article.get("source", {}).get("name", "")
                    headlines.append(f"{idx+1}. {title} [{source}]")
                
                return "Here are the top news headlines:\n" + "\n".join(headlines)
            elif resp.status_code == 426:
                # Developer key may need "us" country or sources filter
                url2 = f"https://newsapi.org/v2/top-headlines?sources=bbc-news,cnn,the-times-of-india&pageSize=5&apiKey={self.config.NEWS_API_KEY}"
                resp2 = requests.get(url2, timeout=5)
                if resp2.status_code == 200:
                    data = resp2.json()
                    articles = data.get("articles", [])
                    headlines = [f"{i+1}. {a.get('title','')} [{a.get('source',{}).get('name','')}]" for i, a in enumerate(articles[:5])]
                    return "Here are the top news headlines:\n" + "\n".join(headlines)
            return f"News API returned an error: {resp.status_code} — {resp.text[:100]}"

        except Exception as e:
            self.logger.warning(f"News check error: {e}")
            return "Unable to fetch the latest news at this time."

    def read_latest_emails(self, count: int = 3) -> str:
        """Connects to IMAP and reads the subjects of the latest unread emails."""
        addr = getattr(self.config, 'EMAIL_ADDRESS', "")
        pwd = getattr(self.config, 'EMAIL_APP_PASSWORD', "")
        
        if not addr or not pwd:
            return "Email credentials are not configured. Please add EMAIL_ADDRESS and EMAIL_APP_PASSWORD to your .env file."
        
        try:
            # Connect to the server
            mail = imaplib.IMAP4_SSL("imap.gmail.com")
            mail.login(addr, pwd)
            mail.select("inbox")
            
            # Search for unread emails
            status, messages = mail.search(None, "UNSEEN")
            if status != "OK":
                return "Could not search your inbox."
            
            email_ids = messages[0].split()
            if not email_ids:
                return "You have no new unread emails."
            
            latest_ids = email_ids[-count:]
            summaries = []
            
            for eid in latest_ids:
                res, msg_data = mail.fetch(eid, "(RFC822)")
                for response_part in msg_data:
                    if isinstance(response_part, tuple):
                        msg = email.message_from_bytes(response_part[1])
                        
                        # Decode subject
                        subject, encoding = decode_header(msg["Subject"])[0]
                        if isinstance(subject, bytes):
                            subject = subject.decode(encoding if encoding else "utf-8", errors="ignore")
                            
                        # Decode sender
                        sender, encoding = decode_header(msg.get("From"))[0]
                        if isinstance(sender, bytes):
                            sender = sender.decode(encoding if encoding else "utf-8", errors="ignore")
                            
                        # Clean sender format (e.g., "Name <email@domain.com>")
                        clean_sender = sender.split("<")[0].strip()
                        summaries.append(f"From {clean_sender}: {subject}")
            
            mail.logout()
            
            return f"You have {len(email_ids)} unread emails. Here are the latest {len(summaries)}:\n" + "\n".join(summaries)
            
        except imaplib.IMAP4.error as e:
            self.logger.error(f"IMAP Login failed: {e}")
            return "Failed to log in to your email. Ensure you are using an App Password and IMAP is enabled in your Gmail settings."
        except Exception as e:
            self.logger.error(f"Email fetch error: {e}")
            return "An error occurred while trying to read your emails."

    def get_joke(self) -> str:
        """Pulls a random safe joke from JokeAPI"""
        try:
            self.logger.info("Fetching a funny joke from the ether...")
            resp = requests.get("https://v2.jokeapi.dev/joke/Any?safe-mode&type=single", timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                if not data.get("error", False):
                    return data.get("joke", "I ran out of jokes.")
            
            # Fallback to another joke API
            resp = requests.get("https://official-joke-api.appspot.com/random_joke", timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                return f"{data.get('setup')} ... {data.get('punchline')}"
            return "Why did the computer go to the doctor? Because it had a virus!"
        except Exception as e:
            self.logger.warning(f"Joke fetch error: {e}")
            return "My humor module is currently offline."

    def get_definition(self, word: str) -> str:
        """Fetches dictionary definition for a word"""
        try:
            self.logger.info(f"Looking up dictionary definition for '{word}'...")
            resp = requests.get(f"https://api.dictionaryapi.dev/api/v2/entries/en/{word}", timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                meanings = data[0].get("meanings", [])
                if meanings:
                    definition = meanings[0].get("definitions", [{}])[0].get("definition", "")
                    part_of_speech = meanings[0].get("partOfSpeech", "noun")
                    return f"{word.capitalize()} ({part_of_speech}): {definition}"
            return f"I couldn't find a definition for the word '{word}'."
        except Exception as e:
            self.logger.warning(f"Dictionary API error: {e}")
            return f"Could not look up definitions right now."

    def get_quote(self) -> str:
        """Pulls a motivational quote from ZenQuotes API"""
        try:
            self.logger.info("Fetching a motivational quote...")
            resp = requests.get("https://zenquotes.io/api/random", timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, list) and len(data) > 0:
                    quote = data[0].get("q", "")
                    author = data[0].get("a", "Unknown")
                    return f"\"{quote}\" — {author}"
            return "Believe you can and you're halfway there. — Theodore Roosevelt"
        except Exception as e:
            self.logger.warning(f"Quote fetch error: {e}")
            return "Keep moving forward, no matter what."

    def convert_currency(self, amount: float, from_curr: str, to_curr: str) -> str:
        """Converts an amount of currency to another using exchange rates"""
        try:
            from_c = from_curr.upper().strip()
            to_c = to_curr.upper().strip()
            self.logger.info(f"Converting {amount} {from_c} to {to_c}...")
            resp = requests.get(f"https://open.er-api.com/v6/latest/{from_c}", timeout=5)
            if resp.status_code == 200:
                rates = resp.json().get("rates", {})
                rate = rates.get(to_c)
                if rate:
                    converted = amount * rate
                    return f"{amount} {from_c} is approximately {converted:.2f} {to_c}."
                return f"Exchange rate for {to_c} was not found."
            return "Unable to fetch currency exchange rates."
        except Exception as e:
            self.logger.warning(f"Currency converter error: {e}")
            return "Currency conversion sensor failed."
