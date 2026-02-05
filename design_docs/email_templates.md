# Email Templates Specification

## Overview

This document specifies all email templates for Curious Now, including transactional emails (magic links, confirmations) and marketing emails (digests, notifications).

---

## Email Design System

### Brand Colors

```css
:root {
  --primary-blue: #1a4d7c;
  --accent-teal: #2d8a8a;
  --text-primary: #1a202c;
  --text-secondary: #4a5568;
  --background: #ffffff;
  --background-alt: #f8f9fa;
  --border: #e2e8f0;
  --success: #38a169;
  --warning: #d69e2e;
  --error: #e53e3e;
}
```

### Typography

- **Headings**: Georgia, 'Times New Roman', serif
- **Body**: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif
- **Code**: 'SF Mono', Monaco, monospace

### Email Width

- Max width: 600px
- Padding: 24px (mobile: 16px)
- Border radius: 8px

---

## Base Template

All emails extend this base template structure.

```html
<!DOCTYPE html>
<html lang="en" xmlns:v="urn:schemas-microsoft-com:vml">
<head>
  <meta charset="utf-8">
  <meta name="x-apple-disable-message-reformatting">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="format-detection" content="telephone=no, date=no, address=no, email=no, url=no">
  <meta name="color-scheme" content="light dark">
  <meta name="supported-color-schemes" content="light dark">
  <!--[if mso]>
  <noscript>
    <xml>
      <o:OfficeDocumentSettings xmlns:o="urn:schemas-microsoft-com:office:office">
        <o:PixelsPerInch>96</o:PixelsPerInch>
      </o:OfficeDocumentSettings>
    </xml>
  </noscript>
  <style>
    td,th,div,p,a,h1,h2,h3,h4,h5,h6 {font-family: "Segoe UI", sans-serif; mso-line-height-rule: exactly;}
  </style>
  <![endif]-->
  <title>{{ subject }}</title>
  <style>
    /* Reset */
    img { border: 0; height: auto; line-height: 100%; outline: none; text-decoration: none; }
    table { border-collapse: collapse !important; }
    body { height: 100% !important; margin: 0 !important; padding: 0 !important; width: 100% !important; }

    /* iOS blue links */
    a[x-apple-data-detectors] {
      color: inherit !important;
      text-decoration: none !important;
      font-size: inherit !important;
      font-family: inherit !important;
      font-weight: inherit !important;
      line-height: inherit !important;
    }

    /* Gmail blue links */
    u + #body a { color: inherit; text-decoration: none; font-size: inherit; font-family: inherit; font-weight: inherit; line-height: inherit; }

    /* Samsung Mail */
    #MessageViewBody a { color: inherit; text-decoration: none; font-size: inherit; font-family: inherit; font-weight: inherit; line-height: inherit; }

    /* Dark mode */
    @media (prefers-color-scheme: dark) {
      .dark-bg { background-color: #1a202c !important; }
      .dark-text { color: #e2e8f0 !important; }
      .dark-text-secondary { color: #a0aec0 !important; }
    }

    /* Mobile */
    @media only screen and (max-width: 600px) {
      .container { width: 100% !important; padding: 16px !important; }
      .mobile-padding { padding: 16px !important; }
      .mobile-full-width { width: 100% !important; }
      .mobile-center { text-align: center !important; }
      .mobile-hide { display: none !important; }
    }
  </style>
</head>
<body id="body" style="margin: 0; padding: 0; word-spacing: normal; background-color: #f8f9fa;">
  <div role="article" aria-roledescription="email" aria-label="{{ subject }}" lang="en" style="text-size-adjust: 100%; -webkit-text-size-adjust: 100%; -ms-text-size-adjust: 100%;">

    <!-- Preheader -->
    <div style="display: none; max-height: 0; overflow: hidden; mso-hide: all;">
      {{ preheader }}
      &#847;&zwnj;&nbsp;&#847;&zwnj;&nbsp;&#847;&zwnj;&nbsp;&#847;&zwnj;&nbsp;&#847;&zwnj;&nbsp;&#847;&zwnj;&nbsp;
    </div>

    <!-- Email Container -->
    <table role="presentation" style="width: 100%; border: 0; cellpadding: 0; cellspacing: 0; background-color: #f8f9fa;" class="dark-bg">
      <tr>
        <td align="center" style="padding: 40px 20px;">

          <!-- Main Content -->
          <table role="presentation" class="container" style="width: 600px; max-width: 600px; border: 0; cellpadding: 0; cellspacing: 0; background-color: #ffffff; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.1);">

            <!-- Header -->
            <tr>
              <td style="padding: 32px 40px 24px 40px; text-align: center; border-bottom: 1px solid #e2e8f0;">
                <a href="https://curious.now" style="text-decoration: none;">
                  <img src="https://curious.now/logo.png" alt="Curious Now" width="160" height="40" style="display: block; margin: 0 auto;">
                </a>
              </td>
            </tr>

            <!-- Body Content -->
            <tr>
              <td class="mobile-padding" style="padding: 40px;">
                {{ content }}
              </td>
            </tr>

            <!-- Footer -->
            <tr>
              <td style="padding: 24px 40px; background-color: #f8f9fa; border-radius: 0 0 8px 8px; border-top: 1px solid #e2e8f0;">
                <table role="presentation" style="width: 100%; border: 0; cellpadding: 0; cellspacing: 0;">
                  <tr>
                    <td style="text-align: center; padding-bottom: 16px;">
                      <a href="https://twitter.com/curiousnow" style="display: inline-block; margin: 0 8px;">
                        <img src="https://curious.now/email/twitter.png" alt="Twitter" width="24" height="24">
                      </a>
                      <a href="https://github.com/curious-now" style="display: inline-block; margin: 0 8px;">
                        <img src="https://curious.now/email/github.png" alt="GitHub" width="24" height="24">
                      </a>
                    </td>
                  </tr>
                  <tr>
                    <td style="text-align: center; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; font-size: 12px; color: #718096; line-height: 1.5;">
                      <p style="margin: 0 0 8px 0;">
                        Curious Now - Science news that makes you think
                      </p>
                      <p style="margin: 0 0 8px 0;">
                        <a href="{{ unsubscribe_url }}" style="color: #718096; text-decoration: underline;">Unsubscribe</a> ·
                        <a href="https://curious.now/settings" style="color: #718096; text-decoration: underline;">Email Settings</a> ·
                        <a href="https://curious.now/privacy" style="color: #718096; text-decoration: underline;">Privacy</a>
                      </p>
                      <p style="margin: 0; color: #a0aec0;">
                        © {{ year }} Curious Now. All rights reserved.
                      </p>
                    </td>
                  </tr>
                </table>
              </td>
            </tr>

          </table>

        </td>
      </tr>
    </table>

  </div>
</body>
</html>
```

---

## Transactional Emails

### 1. Magic Link Login

**Subject:** `Sign in to Curious Now`

**Preheader:** `Click the link to sign in - expires in 15 minutes`

```html
<!-- Content Block -->
<h1 style="margin: 0 0 24px 0; font-family: Georgia, 'Times New Roman', serif; font-size: 28px; font-weight: 600; color: #1a202c; line-height: 1.3;">
  Sign in to Curious Now
</h1>

<p style="margin: 0 0 24px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; font-size: 16px; color: #4a5568; line-height: 1.6;">
  Click the button below to sign in to your account. This link will expire in 15 minutes.
</p>

<!-- CTA Button -->
<table role="presentation" style="width: 100%; border: 0; cellpadding: 0; cellspacing: 0; margin: 32px 0;">
  <tr>
    <td align="center">
      <a href="{{ magic_link_url }}" style="display: inline-block; padding: 16px 32px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; font-size: 16px; font-weight: 600; color: #ffffff; background-color: #1a4d7c; border-radius: 8px; text-decoration: none; mso-padding-alt: 0;">
        <!--[if mso]>
        <i style="letter-spacing: 32px; mso-font-width: -100%; mso-text-raise: 30pt;">&nbsp;</i>
        <![endif]-->
        <span style="mso-text-raise: 15pt;">Sign In</span>
        <!--[if mso]>
        <i style="letter-spacing: 32px; mso-font-width: -100%;">&nbsp;</i>
        <![endif]-->
      </a>
    </td>
  </tr>
</table>

<p style="margin: 0 0 16px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; font-size: 14px; color: #718096; line-height: 1.6;">
  Or copy and paste this link into your browser:
</p>

<p style="margin: 0 0 24px 0; font-family: 'SF Mono', Monaco, monospace; font-size: 12px; color: #4a5568; line-height: 1.6; word-break: break-all; background-color: #f8f9fa; padding: 12px; border-radius: 4px;">
  {{ magic_link_url }}
</p>

<!-- Security Notice -->
<table role="presentation" style="width: 100%; border: 0; cellpadding: 0; cellspacing: 0; background-color: #fef3c7; border-radius: 8px; margin-top: 32px;">
  <tr>
    <td style="padding: 16px;">
      <p style="margin: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; font-size: 14px; color: #92400e; line-height: 1.5;">
        <strong>Security tip:</strong> If you didn't request this email, you can safely ignore it. Someone may have entered your email address by mistake.
      </p>
    </td>
  </tr>
</table>
```

**Backend Template Variables:**
```python
{
    "magic_link_url": str,  # Full magic link URL with token
    "user_email": str,      # User's email address
    "ip_address": str,      # Request IP (optional, for security)
    "user_agent": str,      # Browser info (optional)
    "expires_at": datetime, # Link expiration time
}
```

---

### 2. Welcome Email (After First Sign-in)

**Subject:** `Welcome to Curious Now!`

**Preheader:** `Your journey into science starts here`

```html
<h1 style="margin: 0 0 24px 0; font-family: Georgia, 'Times New Roman', serif; font-size: 28px; font-weight: 600; color: #1a202c; line-height: 1.3;">
  Welcome to Curious Now! 🎉
</h1>

<p style="margin: 0 0 24px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; font-size: 16px; color: #4a5568; line-height: 1.6;">
  We're excited to have you join our community of curious minds. Here's what you can do:
</p>

<!-- Feature List -->
<table role="presentation" style="width: 100%; border: 0; cellpadding: 0; cellspacing: 0; margin: 24px 0;">
  <!-- Feature 1 -->
  <tr>
    <td style="padding: 16px 0; border-bottom: 1px solid #e2e8f0;">
      <table role="presentation" style="width: 100%; border: 0; cellpadding: 0; cellspacing: 0;">
        <tr>
          <td style="width: 48px; vertical-align: top;">
            <div style="width: 40px; height: 40px; background-color: #ebf8ff; border-radius: 8px; text-align: center; line-height: 40px; font-size: 20px;">
              📰
            </div>
          </td>
          <td style="vertical-align: top; padding-left: 16px;">
            <h3 style="margin: 0 0 4px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; font-size: 16px; font-weight: 600; color: #1a202c;">
              Browse the Feed
            </h3>
            <p style="margin: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; font-size: 14px; color: #718096; line-height: 1.5;">
              Explore curated science stories from multiple sources, clustered by topic for easy comparison.
            </p>
          </td>
        </tr>
      </table>
    </td>
  </tr>

  <!-- Feature 2 -->
  <tr>
    <td style="padding: 16px 0; border-bottom: 1px solid #e2e8f0;">
      <table role="presentation" style="width: 100%; border: 0; cellpadding: 0; cellspacing: 0;">
        <tr>
          <td style="width: 48px; vertical-align: top;">
            <div style="width: 40px; height: 40px; background-color: #f0fff4; border-radius: 8px; text-align: center; line-height: 40px; font-size: 20px;">
              💾
            </div>
          </td>
          <td style="vertical-align: top; padding-left: 16px;">
            <h3 style="margin: 0 0 4px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; font-size: 16px; font-weight: 600; color: #1a202c;">
              Save for Later
            </h3>
            <p style="margin: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; font-size: 14px; color: #718096; line-height: 1.5;">
              Bookmark interesting stories to read later, even when you're offline.
            </p>
          </td>
        </tr>
      </table>
    </td>
  </tr>

  <!-- Feature 3 -->
  <tr>
    <td style="padding: 16px 0;">
      <table role="presentation" style="width: 100%; border: 0; cellpadding: 0; cellspacing: 0;">
        <tr>
          <td style="width: 48px; vertical-align: top;">
            <div style="width: 40px; height: 40px; background-color: #faf5ff; border-radius: 8px; text-align: center; line-height: 40px; font-size: 20px;">
              🔔
            </div>
          </td>
          <td style="vertical-align: top; padding-left: 16px;">
            <h3 style="margin: 0 0 4px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; font-size: 16px; font-weight: 600; color: #1a202c;">
              Follow Topics
            </h3>
            <p style="margin: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; font-size: 14px; color: #718096; line-height: 1.5;">
              Get personalized recommendations based on your interests.
            </p>
          </td>
        </tr>
      </table>
    </td>
  </tr>
</table>

<!-- CTA -->
<table role="presentation" style="width: 100%; border: 0; cellpadding: 0; cellspacing: 0; margin: 32px 0;">
  <tr>
    <td align="center">
      <a href="https://curious.now" style="display: inline-block; padding: 16px 32px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; font-size: 16px; font-weight: 600; color: #ffffff; background-color: #1a4d7c; border-radius: 8px; text-decoration: none;">
        Start Exploring
      </a>
    </td>
  </tr>
</table>

<p style="margin: 32px 0 0 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; font-size: 14px; color: #718096; line-height: 1.6; text-align: center;">
  Have questions? Just reply to this email—we're here to help.
</p>
```

---

### 3. Email Verification

**Subject:** `Verify your email address`

**Preheader:** `Please verify your email to complete signup`

```html
<h1 style="margin: 0 0 24px 0; font-family: Georgia, 'Times New Roman', serif; font-size: 28px; font-weight: 600; color: #1a202c; line-height: 1.3;">
  Verify your email
</h1>

<p style="margin: 0 0 24px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; font-size: 16px; color: #4a5568; line-height: 1.6;">
  Hi {{ user_name }},
</p>

<p style="margin: 0 0 24px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; font-size: 16px; color: #4a5568; line-height: 1.6;">
  Please verify your email address by clicking the button below. This helps us ensure the security of your account.
</p>

<table role="presentation" style="width: 100%; border: 0; cellpadding: 0; cellspacing: 0; margin: 32px 0;">
  <tr>
    <td align="center">
      <a href="{{ verification_url }}" style="display: inline-block; padding: 16px 32px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; font-size: 16px; font-weight: 600; color: #ffffff; background-color: #38a169; border-radius: 8px; text-decoration: none;">
        Verify Email Address
      </a>
    </td>
  </tr>
</table>

<p style="margin: 0 0 16px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; font-size: 14px; color: #718096; line-height: 1.6;">
  This link will expire in 24 hours.
</p>
```

---

## Marketing Emails

### 4. Daily/Weekly Digest

**Subject:** `Your {{ frequency }} Science Digest - {{ date }}`

**Preheader:** `{{ top_story_headline }}`

```html
<h1 style="margin: 0 0 8px 0; font-family: Georgia, 'Times New Roman', serif; font-size: 24px; font-weight: 600; color: #1a202c; line-height: 1.3;">
  Your {{ frequency }} Digest
</h1>

<p style="margin: 0 0 32px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; font-size: 14px; color: #718096;">
  {{ date }}
</p>

<!-- Featured Story -->
<table role="presentation" style="width: 100%; border: 0; cellpadding: 0; cellspacing: 0; margin-bottom: 32px;">
  <tr>
    <td style="background-color: #f8f9fa; border-radius: 8px; overflow: hidden;">
      {% if featured_story.image_url %}
      <img src="{{ featured_story.image_url }}" alt="" style="width: 100%; height: 200px; object-fit: cover; display: block;">
      {% endif %}
      <div style="padding: 24px;">
        <span style="display: inline-block; padding: 4px 8px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; font-size: 11px; font-weight: 600; color: #1a4d7c; background-color: #ebf8ff; border-radius: 4px; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 12px;">
          Featured
        </span>
        <h2 style="margin: 12px 0 8px 0; font-family: Georgia, 'Times New Roman', serif; font-size: 20px; font-weight: 600; color: #1a202c; line-height: 1.4;">
          <a href="{{ featured_story.url }}" style="color: #1a202c; text-decoration: none;">
            {{ featured_story.headline }}
          </a>
        </h2>
        <p style="margin: 0 0 16px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; font-size: 14px; color: #4a5568; line-height: 1.6;">
          {{ featured_story.takeaway }}
        </p>
        <p style="margin: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; font-size: 12px; color: #718096;">
          {{ featured_story.source_count }} sources · {{ featured_story.topic }}
        </p>
      </div>
    </td>
  </tr>
</table>

<!-- More Stories -->
<h3 style="margin: 0 0 16px 0; font-family: Georgia, 'Times New Roman', serif; font-size: 18px; font-weight: 600; color: #1a202c; border-bottom: 2px solid #e2e8f0; padding-bottom: 8px;">
  More Stories
</h3>

{% for story in stories %}
<table role="presentation" style="width: 100%; border: 0; cellpadding: 0; cellspacing: 0; margin-bottom: 24px;">
  <tr>
    <td style="padding-bottom: 24px; border-bottom: 1px solid #e2e8f0;">
      <table role="presentation" style="width: 100%; border: 0; cellpadding: 0; cellspacing: 0;">
        <tr>
          <td style="vertical-align: top;">
            <span style="display: inline-block; padding: 2px 6px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; font-size: 10px; font-weight: 500; color: #2d8a8a; background-color: #e6fffa; border-radius: 3px; margin-bottom: 8px;">
              {{ story.topic }}
            </span>
            <h4 style="margin: 8px 0 4px 0; font-family: Georgia, 'Times New Roman', serif; font-size: 16px; font-weight: 600; color: #1a202c; line-height: 1.4;">
              <a href="{{ story.url }}" style="color: #1a202c; text-decoration: none;">
                {{ story.headline }}
              </a>
            </h4>
            <p style="margin: 0 0 8px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; font-size: 13px; color: #4a5568; line-height: 1.5;">
              {{ story.takeaway | truncate(120) }}
            </p>
            <p style="margin: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; font-size: 11px; color: #a0aec0;">
              {{ story.source_count }} sources
            </p>
          </td>
          {% if story.thumbnail_url %}
          <td style="width: 100px; vertical-align: top; padding-left: 16px;" class="mobile-hide">
            <img src="{{ story.thumbnail_url }}" alt="" style="width: 100px; height: 75px; object-fit: cover; border-radius: 4px;">
          </td>
          {% endif %}
        </tr>
      </table>
    </td>
  </tr>
</table>
{% endfor %}

<!-- View All CTA -->
<table role="presentation" style="width: 100%; border: 0; cellpadding: 0; cellspacing: 0; margin: 32px 0;">
  <tr>
    <td align="center">
      <a href="https://curious.now" style="display: inline-block; padding: 14px 28px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; font-size: 14px; font-weight: 600; color: #1a4d7c; background-color: #ffffff; border: 2px solid #1a4d7c; border-radius: 8px; text-decoration: none;">
        View All Stories →
      </a>
    </td>
  </tr>
</table>

<!-- Digest Settings -->
<table role="presentation" style="width: 100%; border: 0; cellpadding: 0; cellspacing: 0; background-color: #f8f9fa; border-radius: 8px; margin-top: 32px;">
  <tr>
    <td style="padding: 16px; text-align: center;">
      <p style="margin: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; font-size: 13px; color: #718096;">
        Receiving this {{ frequency }}?
        <a href="{{ settings_url }}" style="color: #1a4d7c; text-decoration: underline;">
          Change digest frequency
        </a>
      </p>
    </td>
  </tr>
</table>
```

**Backend Template Variables:**
```python
{
    "frequency": str,  # "daily" or "weekly"
    "date": str,       # "January 15, 2025"
    "featured_story": {
        "headline": str,
        "takeaway": str,
        "url": str,
        "image_url": str | None,
        "source_count": int,
        "topic": str,
    },
    "stories": List[{
        "headline": str,
        "takeaway": str,
        "url": str,
        "thumbnail_url": str | None,
        "source_count": int,
        "topic": str,
    }],
    "settings_url": str,
}
```

---

### 5. Topic Alert

**Subject:** `New story in {{ topic }}: {{ headline }}`

**Preheader:** `{{ takeaway | truncate(100) }}`

```html
<table role="presentation" style="width: 100%; border: 0; cellpadding: 0; cellspacing: 0; margin-bottom: 24px;">
  <tr>
    <td>
      <span style="display: inline-block; padding: 6px 12px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; font-size: 12px; font-weight: 600; color: #1a4d7c; background-color: #ebf8ff; border-radius: 16px;">
        📢 {{ topic }} Alert
      </span>
    </td>
  </tr>
</table>

<h1 style="margin: 0 0 16px 0; font-family: Georgia, 'Times New Roman', serif; font-size: 24px; font-weight: 600; color: #1a202c; line-height: 1.3;">
  {{ headline }}
</h1>

<p style="margin: 0 0 24px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; font-size: 16px; color: #4a5568; line-height: 1.6;">
  {{ takeaway }}
</p>

<!-- Story Meta -->
<table role="presentation" style="width: 100%; border: 0; cellpadding: 0; cellspacing: 0; margin-bottom: 24px;">
  <tr>
    <td style="padding: 16px; background-color: #f8f9fa; border-radius: 8px;">
      <table role="presentation" style="width: 100%; border: 0; cellpadding: 0; cellspacing: 0;">
        <tr>
          <td style="width: 50%; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; font-size: 13px; color: #718096;">
            <strong style="color: #4a5568;">Sources:</strong> {{ source_count }}
          </td>
          <td style="width: 50%; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; font-size: 13px; color: #718096; text-align: right;">
            <strong style="color: #4a5568;">Confidence:</strong> {{ confidence_level }}
          </td>
        </tr>
      </table>
    </td>
  </tr>
</table>

<table role="presentation" style="width: 100%; border: 0; cellpadding: 0; cellspacing: 0; margin: 32px 0;">
  <tr>
    <td align="center">
      <a href="{{ story_url }}" style="display: inline-block; padding: 16px 32px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; font-size: 16px; font-weight: 600; color: #ffffff; background-color: #1a4d7c; border-radius: 8px; text-decoration: none;">
        Read Full Story
      </a>
    </td>
  </tr>
</table>

<p style="margin: 32px 0 0 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; font-size: 13px; color: #a0aec0; text-align: center;">
  You're receiving this because you follow <strong>{{ topic }}</strong>.
  <a href="{{ unfollow_url }}" style="color: #718096; text-decoration: underline;">Unfollow</a>
</p>
```

---

### 6. Re-engagement Email

**Subject:** `We miss you! Here's what's new in science`

**Preheader:** `Catch up on the latest discoveries`

```html
<h1 style="margin: 0 0 24px 0; font-family: Georgia, 'Times New Roman', serif; font-size: 28px; font-weight: 600; color: #1a202c; line-height: 1.3;">
  A lot has happened since you've been away! 🔬
</h1>

<p style="margin: 0 0 24px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; font-size: 16px; color: #4a5568; line-height: 1.6;">
  Hi {{ user_name }},
</p>

<p style="margin: 0 0 24px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; font-size: 16px; color: #4a5568; line-height: 1.6;">
  It's been {{ days_since_visit }} days since your last visit. Here are some stories we think you'd find interesting:
</p>

<!-- Top Stories Summary -->
<table role="presentation" style="width: 100%; border: 0; cellpadding: 0; cellspacing: 0; margin: 24px 0;">
  {% for story in top_stories %}
  <tr>
    <td style="padding: 16px 0; border-bottom: 1px solid #e2e8f0;">
      <span style="display: inline-block; padding: 2px 6px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; font-size: 10px; font-weight: 500; color: #2d8a8a; background-color: #e6fffa; border-radius: 3px;">
        {{ story.topic }}
      </span>
      <h3 style="margin: 8px 0 4px 0; font-family: Georgia, 'Times New Roman', serif; font-size: 16px; font-weight: 600; color: #1a202c; line-height: 1.4;">
        <a href="{{ story.url }}" style="color: #1a202c; text-decoration: none;">
          {{ story.headline }}
        </a>
      </h3>
    </td>
  </tr>
  {% endfor %}
</table>

<table role="presentation" style="width: 100%; border: 0; cellpadding: 0; cellspacing: 0; margin: 32px 0;">
  <tr>
    <td align="center">
      <a href="https://curious.now" style="display: inline-block; padding: 16px 32px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; font-size: 16px; font-weight: 600; color: #ffffff; background-color: #1a4d7c; border-radius: 8px; text-decoration: none;">
        Catch Up Now
      </a>
    </td>
  </tr>
</table>

<!-- Unsubscribe note -->
<p style="margin: 32px 0 0 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; font-size: 13px; color: #a0aec0; text-align: center;">
  Not interested anymore? <a href="{{ unsubscribe_url }}" style="color: #718096; text-decoration: underline;">Unsubscribe from re-engagement emails</a>
</p>
```

---

## Plain Text Versions

Every HTML email must have a plain text alternative.

### Magic Link (Plain Text)

```
Sign in to Curious Now
======================

Click the link below to sign in to your account. This link will expire in 15 minutes.

{{ magic_link_url }}

Security tip: If you didn't request this email, you can safely ignore it. Someone may have entered your email address by mistake.

---
Curious Now - Science news that makes you think
https://curious.now

Unsubscribe: {{ unsubscribe_url }}
```

### Digest (Plain Text)

```
Your {{ frequency }} Digest - {{ date }}
========================================

FEATURED: {{ featured_story.headline }}
{{ featured_story.takeaway }}
{{ featured_story.source_count }} sources · {{ featured_story.topic }}
Read more: {{ featured_story.url }}

---

MORE STORIES

{% for story in stories %}
{{ story.topic | upper }}
{{ story.headline }}
{{ story.takeaway }}
{{ story.source_count }} sources
Read more: {{ story.url }}

{% endfor %}

---

View all stories: https://curious.now
Change digest settings: {{ settings_url }}
Unsubscribe: {{ unsubscribe_url }}

---
Curious Now - Science news that makes you think
© {{ year }} Curious Now. All rights reserved.
```

---

## Email Service Integration

### SendGrid Template Configuration

```python
# src/services/email.py

from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, Personalization
from jinja2 import Environment, FileSystemLoader

class EmailService:
    def __init__(self, api_key: str):
        self.client = SendGridAPIClient(api_key)
        self.jinja_env = Environment(
            loader=FileSystemLoader('templates/email'),
            autoescape=True
        )

    async def send_magic_link(
        self,
        to_email: str,
        magic_link_url: str,
        ip_address: str | None = None
    ) -> bool:
        """Send magic link authentication email."""
        template = self.jinja_env.get_template('magic_link.html')
        html_content = template.render(
            magic_link_url=magic_link_url,
            ip_address=ip_address,
            year=datetime.now().year,
            unsubscribe_url=f"https://curious.now/unsubscribe?email={to_email}"
        )

        text_template = self.jinja_env.get_template('magic_link.txt')
        text_content = text_template.render(
            magic_link_url=magic_link_url,
            unsubscribe_url=f"https://curious.now/unsubscribe?email={to_email}"
        )

        message = Mail(
            from_email=('hello@curious.now', 'Curious Now'),
            to_emails=to_email,
            subject='Sign in to Curious Now',
            html_content=html_content,
            plain_text_content=text_content
        )

        # Add headers for tracking
        message.header = {
            'X-Entity-Ref-ID': str(uuid.uuid4()),
            'List-Unsubscribe': f'<https://curious.now/unsubscribe?email={to_email}>'
        }

        response = await self.client.send(message)
        return response.status_code == 202

    async def send_digest(
        self,
        to_email: str,
        frequency: str,
        featured_story: dict,
        stories: list[dict]
    ) -> bool:
        """Send daily or weekly digest email."""
        template = self.jinja_env.get_template('digest.html')
        html_content = template.render(
            frequency=frequency,
            date=datetime.now().strftime('%B %d, %Y'),
            featured_story=featured_story,
            stories=stories,
            settings_url=f"https://curious.now/settings/digest?email={to_email}",
            unsubscribe_url=f"https://curious.now/unsubscribe?email={to_email}",
            year=datetime.now().year
        )

        message = Mail(
            from_email=('digest@curious.now', 'Curious Now Digest'),
            to_emails=to_email,
            subject=f"Your {frequency} Science Digest - {datetime.now().strftime('%B %d')}",
            html_content=html_content
        )

        # Categories for filtering
        message.category = [f'{frequency}-digest', 'marketing']

        response = await self.client.send(message)
        return response.status_code == 202
```

---

## Testing Checklist

### Email Client Testing

Test all templates in:
- [ ] Gmail (Web)
- [ ] Gmail (iOS/Android app)
- [ ] Apple Mail (macOS)
- [ ] Apple Mail (iOS)
- [ ] Outlook (Windows desktop)
- [ ] Outlook (Web)
- [ ] Outlook (iOS/Android app)
- [ ] Yahoo Mail
- [ ] Samsung Mail (Android)

### Rendering Tests

- [ ] Images display correctly (with alt text as fallback)
- [ ] Links are clickable and correct
- [ ] Text is readable without images
- [ ] Dark mode displays correctly
- [ ] Mobile layout is responsive (320px-480px width)
- [ ] Plain text version is readable
- [ ] Preheader text appears correctly

### Deliverability Tests

- [ ] SPF record configured
- [ ] DKIM signing enabled
- [ ] DMARC policy set
- [ ] Not flagged as spam
- [ ] Unsubscribe link works
- [ ] List-Unsubscribe header present

### Accessibility Tests

- [ ] Semantic HTML structure
- [ ] Sufficient color contrast (4.5:1 minimum)
- [ ] Link text is descriptive
- [ ] Images have alt text
- [ ] Content readable at 200% zoom
