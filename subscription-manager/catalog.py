"""Known vendors: where to manage / cancel, and how.

Each entry is matched against a subscription's name/vendor/channel (lower-case
substring match). The first match wins, so put specific entries before
generic ones.
"""

GOOGLE_PLAY_URL = "https://play.google.com/store/account/subscriptions"
APPLE_URL = "https://apps.apple.com/account/subscriptions"
PADDLE_URL = "https://customer-portal.paddle.com"
PAYPAL_URL = "https://www.paypal.com/myaccount/autopay/"

CATALOG = [
    # key substrings, manage url, cancel email, how-to (Turkish)
    (("google play",), GOOGLE_PLAY_URL, "",
     "Google Play > Ödemeler ve abonelikler > Abonelikler. Aboneliği seçip 'Aboneliği iptal et'e bas. "
     "Telefonda: Play Store > profil > Ödemeler ve abonelikler."),
    (("apple", "icloud"), APPLE_URL, "",
     "iPhone: Ayarlar > [adın] > Abonelikler. iCloud depolama için: Ayarlar > [adın] > iCloud > "
     "Depolamayı Yönet > Depolama Planını Değiştir > Ücretsiz plana düşür."),
    (("paddle", "klangio", "butterfly effect"), PADDLE_URL, "help@paddle.com",
     "Paddle müşteri portalına abonelik e-postanla gir (kod e-postayla gelir), aboneliği seçip 'Cancel subscription'."),
    (("suno",), "https://suno.com/account", "billing@suno.com",
     "suno.com > Account > Manage Subscription > Cancel."),
    (("songscription",), "https://songscription.ai", "support@songscription.ai",
     "Hesabına gir > Account / Billing > Cancel plan."),
    (("eleven",), "https://elevenlabs.io/app/subscription", "team@elevenlabs.io",
     "elevenlabs.io > Subscription > Cancel subscription (ya da Free plana düş)."),
    (("x premium", "twitter"), "https://x.com/settings/manage_subscriptions", "paidfeatures@x.com",
     "x.com > Ayarlar > Abonelikleri yönet > Premium > Aboneliği iptal et."),
    (("generatepress",), "https://generatepress.com/account/", "support@generatepress.com",
     "GeneratePress hesabı > Subscriptions > Cancel (lisans dönem sonuna kadar çalışır)."),
    (("formidable",), "https://formidableforms.com/account/", "accounts@formidableforms.com",
     "formidableforms.com/account > Licenses/Subscriptions > Turn off auto-renew / Cancel."),
    (("namecheap",), "https://ap.www.namecheap.com/domains/list/", "support@namecheap.com",
     "Namecheap > Domain List > alan adı > Auto-Renew anahtarını kapat."),
    (("chatgpt", "openai"), "https://chatgpt.com/admin/billing", "",
     "ChatGPT > Workspace settings > Billing > Cancel plan (Business için workspace sahibi yapmalı)."),
    (("microsoft 365", "microsoft"), "https://admin.microsoft.com/adminportal/home#/subscriptions", "",
     "Microsoft 365 yönetim merkezi > Faturalama > Ürünleriniz > abonelik > 'Aboneliği iptal et' "
     "(veya 'Yinelenen faturalamayı kapat')."),
    (("adobe",), "https://account.adobe.com/plans", "",
     "account.adobe.com > Planlar > Planı yönet > Planınızı iptal edin. Erken iptalde ceza ücreti olabilir."),
    (("disney",), "https://www.disneyplus.com/account/subscription", "",
     "Disney+ > Hesap > Abonelik > Aboneliği iptal et."),
    (("abacus",), "https://apps.abacus.ai/chatllm/", "support@abacus.ai",
     "ChatLLM > Profile > Billing / Manage subscription > Cancel."),
    (("tad.ai",), "https://tad.ai", "",
     "tad.ai hesabı > Billing > Cancel. Bulamazsan iptal e-postası gönder."),
    (("wps", "kingsoft"), "https://account.wps.com", "",
     "account.wps.com > Subscription / Order > Cancel auto-renewal."),
    (("updf",), "https://accounts.updf.com", "support@updf.com",
     "UPDF hesabı > Subscription > Cancel auto-renew."),
    (("kling",), "https://klingai.com", "support@kling.ai",
     "klingai.com > profil > Membership / Subscription > Cancel."),
    (("musescore",), "https://musescore.com/user/subscription", "",
     "musescore.com > hesap > Subscription > Cancel (sayfa açılmazsa Ayarlar > Membership)."),
    (("hetzner",), "https://accounts.hetzner.com", "",
     "Hetzner: sunucuyu/ürünü konsoldan sil veya Robot/Accounts'tan iptal et. Silinmeyen kaynak faturalanmaya devam eder."),
    (("netcup",), "https://www.customercontrolpanel.de", "",
     "netcup CCP > Products > ürün > Cancel product (fesih süresine dikkat)."),
    (("cyberpanel",), "https://cyberpanel.net", "",
     "CyberPanel hesabı (cyberpanel.net) > My Account > Subscriptions > Cancel."),
    (("sanal santral",), "", "info@sanalsantral.com.tr",
     "Sözleşmeli hizmet: yazılı fesih bildirimi gönder (taahhüt süresini kontrol et)."),
    (("güzel hosting", "guzel"), "https://www.guzel.net.tr", "",
     "Güzel Hosting müşteri paneli > Hizmetler > İptal talebi."),
    (("türk telekom", "turk telekom"), "https://online.turktelekom.com.tr", "",
     "Kurumsal hat: Türk Telekom kurumsal müşteri hizmetleri veya bayi üzerinden; taahhüt cezası olabilir."),
    (("storytel",), GOOGLE_PLAY_URL, "support@storytel.com", ""),
    (("spanishpod",), "https://www.spanishpod101.com/member/account", "support@spanishpod101.com",
     "SpanishPod101 > Account > Subscriptions > Cancel."),
    (("bookstera",), "https://bookstera.com", "",
     "bookstera.com > Account > Billing > Cancel."),
    (("paypal",), PAYPAL_URL, "",
     "PayPal > Ayarlar > Ödemeler > Otomatik ödemeleri yönet > satıcı > İptal et."),
]


def lookup(*texts):
    """Return (manage_url, cancel_email, how_to) for the first catalog match."""
    hay = " ".join(t for t in texts if t).lower()
    for keys, url, mail, how in CATALOG:
        if any(k in hay for k in keys):
            return url, mail, how
    return "", "", ""


def how_to(item):
    _, _, how = lookup(item.get("channel", ""), item.get("name", ""), item.get("vendor", ""))
    if item.get("channel") == "Google Play":
        _, _, how = lookup("google play")
    elif item.get("channel") == "Apple":
        _, _, how = lookup("apple")
    elif item.get("channel") == "Paddle":
        _, _, how = lookup("paddle")
    return how
