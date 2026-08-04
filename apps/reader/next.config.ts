import type { NextConfig } from "next";

/**
 * Which hosts we will resize an image from.
 *
 * These pictures used to be hotlinked straight from the publisher, on the
 * argument that we should not re-serve someone else's bytes. Measured, that
 * argument fell over: sixty cards of feed pulled 12.9 MB across 29 images, a
 * median of 216 KB and a largest of 3.6 MB — full-resolution paper figures
 * rendered into a card 390px wide, which needs about 25 KB. A browser opens six
 * connections per host, so thirty arXiv figures queue behind each other and the
 * ones further down never arrive at all.
 *
 * So Next fetches each image once, resizes it to the frame it will actually
 * occupy, and serves WebP from its own cache.
 *
 * The list is explicit rather than "**". A wildcard would make this an image
 * proxy for anyone who found the URL. It is also the one thing here that
 * expanding ingestion will silently outgrow: a source whose host is missing
 * degrades to a card with no picture, which is what 48% of stories look like
 * anyway, so nothing appears broken and nothing says so either. Run
 * scripts/v2_image_hosts.py to hear about it.
 */
const IMAGE_HOSTS = [
  "arxiv.org",
  "storage.googleapis.com",
  "lh3.googleusercontent.com",
  "www.mpg.de",
  "ichef.bbci.co.uk",
  "eos.org",
  "cdn.eso.org",
  "www.sciencenews.org",
  "www.quantamagazine.org",
];

const nextConfig: NextConfig = {
  reactStrictMode: true,
  images: {
    remotePatterns: IMAGE_HOSTS.map((hostname) => ({
      protocol: "https" as const,
      hostname,
    })),
    // A published figure does not change. The default of a minute would have us
    // re-fetch a 3.6 MB PNG from arXiv all day.
    minimumCacheTTL: 60 * 60 * 24 * 31,
  },
};

export default nextConfig;
