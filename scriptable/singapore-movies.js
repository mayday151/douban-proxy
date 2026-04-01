// Singapore Events Calendar
// ============================================================
// 把这段代码粘贴到 Scriptable，运行后自动把新加坡即将上映的
// 电影写入 Apple Calendar。
//
// 设置自动运行：iOS 快捷指令 → 自动化 → 每天定时 →
//   添加动作"运行 Scriptable 脚本" → 选此脚本
// ============================================================

// ── 你的设置（按喜好修改）────────────────────────────────
const CONFIG = {
  tmdbApiKey: "298e40de162c0be0d34ea91261a50cde",
  calendarName: "🇸🇬 Singapore Events",   // Apple Calendar 里的日历名
  lookaheadDays: 90,                        // 提前几天抓
  minPopularity: 20,                        // TMDB 人气阈值，越高越严格

  // 想看的电影类型（注释掉不想要的）
  genres: [
    28,   // Action
    878,  // Sci-Fi
    16,   // Animation
    35,   // Comedy
    53,   // Thriller
    // 18,  // Drama
    // 27,  // Horror
    // 10749, // Romance
  ],

  // 这些关键词只要出现在片名就必加，无视类型/人气过滤
  mustWatchKeywords: [
    "Marvel",
    "Avengers",
    "Spider-Man",
    "DC",
    "Batman",
    "Superman",
    "Star Wars",
    "Mission: Impossible",
    "Fast & Furious",
    "John Wick",
    "Jurassic",
    "Alien",
  ],

  // 提前几小时提醒（0 = 不提醒）
  reminderHours: 24,
};
// ────────────────────────────────────────────────────────────

// TMDB genre ID → name
const GENRE_NAMES = {
  28: "Action", 12: "Adventure", 16: "Animation", 35: "Comedy",
  80: "Crime", 99: "Documentary", 18: "Drama", 14: "Fantasy",
  27: "Horror", 10402: "Music", 9648: "Mystery", 10749: "Romance",
  878: "Sci-Fi", 53: "Thriller",
};

// ── Helpers ──────────────────────────────────────────────────

function formatDate(d) {
  return d.toISOString().split("T")[0];
}

function addDays(d, n) {
  const r = new Date(d);
  r.setDate(r.getDate() + n);
  return r;
}

function isMustWatch(title) {
  const t = title.toLowerCase();
  return CONFIG.mustWatchKeywords.some(k => t.includes(k.toLowerCase()));
}

// ── Fetch movies from TMDB ───────────────────────────────────

async function fetchMovies() {
  const today = new Date();
  const end = addDays(today, CONFIG.lookaheadDays);
  const genreParam = CONFIG.genres.join(",");

  let movies = [];
  let page = 1;

  while (true) {
    const url =
      `https://api.themoviedb.org/3/discover/movie` +
      `?api_key=${CONFIG.tmdbApiKey}` +
      `&region=SG` +
      `&primary_release_date.gte=${formatDate(today)}` +
      `&primary_release_date.lte=${formatDate(end)}` +
      `&sort_by=primary_release_date.asc` +
      `&with_genres=${genreParam}` +
      `&page=${page}`;

    const req = new Request(url);
    const data = await req.loadJSON();

    if (!data.results || data.results.length === 0) break;

    for (const m of data.results) {
      if (m.popularity < CONFIG.minPopularity && !isMustWatch(m.title)) continue;
      if (!m.release_date) continue;
      movies.push(m);
    }

    if (page >= (data.total_pages || 1)) break;
    page++;
  }

  // Also fetch must-watch by keyword (bypasses genre filter)
  for (const kw of CONFIG.mustWatchKeywords) {
    const url =
      `https://api.themoviedb.org/3/search/movie` +
      `?api_key=${CONFIG.tmdbApiKey}` +
      `&query=${encodeURIComponent(kw)}` +
      `&region=SG` +
      `&page=1`;
    const req = new Request(url);
    const data = await req.loadJSON();
    for (const m of (data.results || [])) {
      if (!m.release_date) continue;
      const rd = new Date(m.release_date);
      if (rd < today || rd > end) continue;
      if (!movies.find(x => x.id === m.id)) movies.push(m);
    }
  }

  return movies;
}

// ── Write to Apple Calendar ───────────────────────────────────

async function syncToCalendar(movies) {
  // Get or create our calendar
  let calendars = await Calendar.forEvents();
  let cal = calendars.find(c => c.title === CONFIG.calendarName);

  if (!cal) {
    // Scriptable can't create a calendar directly — use default writable calendar
    // and warn the user
    cal = await Calendar.defaultForEvents();
    console.log(`⚠️  Calendar "${CONFIG.calendarName}" not found, using default calendar`);
  }

  // Fetch existing events in the window to avoid duplicates
  const today = new Date();
  const end = addDays(today, CONFIG.lookaheadDays + 1);
  const existing = await CalendarEvent.between(today, end, [cal]);
  const existingTitles = new Set(existing.map(e => e.title));

  let added = 0;
  let skipped = 0;

  for (const movie of movies) {
    const title = `🎬 ${movie.title}`;
    if (existingTitles.has(title)) {
      skipped++;
      continue;
    }

    const releaseDate = new Date(movie.release_date + "T10:00:00"); // 10am SG time

    // Build description
    const genreNames = (movie.genre_ids || [])
      .map(id => GENRE_NAMES[id])
      .filter(Boolean)
      .join(", ");

    const desc = [
      genreNames ? `Genres: ${genreNames}` : "",
      movie.overview ? `\n${movie.overview}` : "",
      `\nhttps://www.themoviedb.org/movie/${movie.id}`,
    ].filter(Boolean).join("");

    const event = new CalendarEvent();
    event.title = title;
    event.calendar = cal;
    event.startDate = releaseDate;
    event.endDate = releaseDate;          // all-day style (same time)
    event.isAllDay = true;
    event.notes = desc;
    event.url = `https://www.themoviedb.org/movie/${movie.id}`;

    if (CONFIG.reminderHours > 0) {
      event.addRecurrenceRule; // no-op, just ensuring field exists
      // Scriptable reminder via alarms
      const alarm = new RecurrenceRule();  // placeholder
      // Note: Scriptable doesn't support alarms directly on CalendarEvent,
      // the reminder will need to be set in Calendar app after import.
    }

    await event.save();
    added++;
    console.log(`✅ Added: ${movie.title} (${movie.release_date})`);
  }

  return { added, skipped, total: movies.length };
}

// ── Main ──────────────────────────────────────────────────────

async function main() {
  console.log("Fetching Singapore movie releases from TMDB...");

  let movies;
  try {
    movies = await fetchMovies();
    console.log(`Found ${movies.length} movies`);
  } catch (e) {
    console.error("TMDB fetch failed:", e.message);
    const alert = new Alert();
    alert.title = "Fetch Failed";
    alert.message = `Could not reach TMDB API:\n${e.message}`;
    alert.addAction("OK");
    await alert.present();
    return;
  }

  const result = await syncToCalendar(movies);

  // Show result notification
  const alert = new Alert();
  alert.title = "🇸🇬 Calendar Updated";
  alert.message =
    `Added ${result.added} new movies\n` +
    `Skipped ${result.skipped} already in calendar\n` +
    `(looked at ${result.total} total)`;
  alert.addAction("OK");
  await alert.present();
}

await main();
