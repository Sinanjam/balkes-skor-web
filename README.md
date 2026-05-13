# Balkes Skor Web

Premium karanlık temalı GitHub Pages sitesi.

## Yayınlama

Fish veya Bash içinde:

```fish
cd ~/Downloads/balkes-skor-web-v0.5-premium-package
bash ./BUILD_PUBLISH_BALKES_SKOR_WEB.sh ~/Downloads/balkes-skor ~/Downloads/balkes-skor-web
```

Script geçici Nix ortamında `git` ve `gh` kullanır. GitHub Actions yoktur.

Önceden bir kez giriş gerekebilir:

```fish
nix-shell -p gh --run 'gh auth login'
```

## Site

https://sinanjam.github.io/balkes-skor-web/

## Sayaç

GoatCounter kodu siteye eklidir:

```html
<script data-goatcounter="https://balkesskor.goatcounter.com/count" async src="//gc.zgo.at/count.js"></script>
```


## Mini güncelleme

Sitede GoatCounter üzerinden `Toplam Ziyaretçi Sayısı` kartı gösterilir. GoatCounter panelinde visitor counter izninin açık olması gerekir.

## Live data fixpack notu

Web `docs/data/` manifest/data_report değerleri canlı veri fixpack ile güncellendi. Android repo `data/` aynı veriyle eşitlendi.
