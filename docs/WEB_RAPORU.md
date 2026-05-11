# Balkes Skor Web v0.5 Raporu

Bu paket Balkes Skor web sitesini günceller.

## Yapılanlar

- Android projesindeki güncel `data/` yapısı web sitesine taşındı.
- Site karanlık, premium görünümlü ve responsive hale getirildi.
- Mobil ve masaüstü kullanım için ayrı grid/akış düzenleri eklendi.
- Sezon kıyası yatay kaydırmalı hale getirildi; sağa kaydırdıkça eski sezonlar görünür.
- Maç listesi, maç detayı, puan durumu, oyuncular ve rakipler bölümleri eklendi/geliştirildi.
- Oyuncu kartına basınca kart içinde detay açılır.
- APK latest release indirme butonu eklendi.
- GoatCounter sayacı eklendi: `balkesskor.goatcounter.com`.
- `.nojekyll` eklendi.

## Veri

Bu paket içinde v0.5 veri yapısı vardır. Yayın script’i çalışırken `~/Downloads/balkes-skor/data` bulunursa web verisini otomatik olarak oradan günceller. Böylece 6 saatlik tarama sonrası uygulama reposuna eklenen yeni veriler web sitesine de taşınır.

## Yayın

Hedef repo:

```text
https://github.com/Sinanjam/balkes-skor-web
```

Hedef site:

```text
https://sinanjam.github.io/balkes-skor-web/
```
