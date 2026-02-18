## Objective
Analyze daily sun rise/set and moon rise/set times across 8 global locations (2020-2025) to generate yearly statistics including:
- Total sun visible days
- Total moon visible days
- Sun-moon overlap periods
- Days with no sun or moon visibility

## Results
* **Raw Data**: [summary.csv](results/summary.csv)
* **Interactive Dashboard**: [dashboard.html](dashboard.html) or [View on CodePen](https://codepen.io/mdileep/full/RNROKvm)

## CSV Columns

### Daily Data Columns

| Column | Description |
|--------|-------------|
| **Date** | Calendar date (YYYY-MM-DD) |
| **Sun-Rise-Time** | Sunrise time in local time (HH:MM:SS) |
| **Sun-Set-Time** | Sunset time in local time (HH:MM:SS) |
| **Total-Sun-Time** | Total daylight duration (H:MM:SS) |
| **Moon-Rise-1-Time** | First moonrise time or blank if at/before midnight |
| **Moon-Set-1-Time** | First moonset time or blank if after midnight |
| **Moon-Rise-2-Time** | Second moonrise time (if moon rises twice in a day) |
| **Moon-Set-2-Time** | Second moonset time (if moon sets twice in a day) |
| **Total-Moon-Time** | Total moon visibility duration (H:MM:SS) |
| **Moon-Phase-Angle** | Moon phase in degrees (0°=new, 90°=first quarter, 180°=full, 270°=last quarter, 360°=new) |
| **Overlap-Sun-Moon-Start-Time** | Start of any sun-moon overlap period |
| **Overlap-Sun-Moon-End-Time** | End of any sun-moon overlap period |
| **Total-Overlap-Time** | Total duration of sun and moon both visible (H:MM:SS) |
| **Total-Moon-Visible-Time** | Moon visibility duration when phase is >30° and <330° (crescent phases) (H:MM:SS) |
| **No-Moon-No-Sun-Start-Time** | Start of darkness period (neither sun nor moon visible) |
| **No-Moon-No-Sun-End-Time** | End of darkness period |
| **Total-No-Moon-No-Sun-Time** | Total darkness duration (H:MM:SS) |
| **Surya-Time** | Pure sun time (sun visible minus visible crescent moon) (H:MM:SS) |
| **Chandra-Time** | Moon time (all lunar visibility) (H:MM:SS) |
| **Agni-Time** | Darkness time (no sun, no moon) (H:MM:SS) |

### Yearly Totals Row

| Column | Description |
|--------|-------------|
| **Location** | "Year Total" |
| **Total-Sun-Days** | Whole number of days of sun visibility |
| **Total-Moon-Days** | Whole number of days of moon visibility |
| **Total-Overlap-Days** | Whole number of days with sun-moon overlap |
| **Total-No-Sun-No-Moon-Days** | Whole number of days with darkness (no sun, no moon) |
| **Surya-Days** | Whole number of days of pure sun time |
| **Chandra-Days** | Whole number of days of moon time |
| **Agni-Days** | Whole number of days of darkness |

### Key Definitions

- **Surya Days**: Sun-only time = Total Sun Time - Moon Visible Time (when moon phase is in crescent)
- **Chandra Days**: Total moon visibility regardless of phase
- **Agni Days**: Complete darkness when neither sun nor moon is visible
