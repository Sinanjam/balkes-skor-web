# Balkes Skor Live Data Fix Report

- Generated: `2026-05-13T03:28:13Z`
- Release oluşturulmadı.
- Android data klasörü web docs/data ile eşitlendi.
- Installed APK ana branch raw data okuyorsa bu push sonrası veri almalıdır.

## İşlemler

- standings_by_week.json kontrol edildi; oluşturulan/düzeltilen: 0
- Web data Android repo içine kopyalandı: `/home/sinanjam/Downloads/balkes-skor-live-fix-work-gh/balkes-skor-web/docs/data` -> `/home/sinanjam/Downloads/balkes-skor-live-fix-work-gh/balkes-skor/data`
- Android data manifest güncellendi: dataBaseUrl `https://raw.githubusercontent.com/Sinanjam/balkes-skor/main/data/` -> `https://raw.githubusercontent.com/Sinanjam/balkes-skor/main/data/`
- Android data manifest dataVersion: 6 -> 7
- Android data manifest appDataVersion: 7 -> 8
- Android data manifest toplam maç: 141
- Web docs/data manifest güncellendi: dataBaseUrl `https://raw.githubusercontent.com/Sinanjam/balkes-skor/main/data/` -> `https://raw.githubusercontent.com/Sinanjam/balkes-skor-web/main/docs/data/`
- Web docs/data manifest dataVersion: 6 -> 7
- Web docs/data manifest appDataVersion: 7 -> 8
- Web docs/data manifest toplam maç: 141
- data_report.json totalAppMatches: 136 -> 141
- data_report.json totalAppMatches: 136 -> 141
- standings_by_week.json kontrol edildi; oluşturulan/düzeltilen: 0
- Android MainActivity BASE_DATA_URL Android repo main/data kaynağına sabitlendi: `app/src/main/java/com/sinanjam/balkesskor/MainActivity.java`
- styles.xml dark Material NoActionBar yapıldı.
- BUILD_PUSH_RELEASE.sh güvenli hale getirildi: workflow silme kaldırıldı, git add . kontrollü listeye çevrildi.
- Web docs/app.js düzeltildi: maç metriği manifest toplamından, yardımcı indeksler fallback ile okunur.
- Android README notu eklendi.
- Web README notu eklendi.
- Android data JSON parse OK.
- Android data sezon dosya bütünlüğü OK.
- Web docs/data JSON parse OK.
- Web docs/data sezon dosya bütünlüğü OK.
