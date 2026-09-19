import { useEffect, useState } from 'react';

import { api, API_BASE } from '../api/client';
import { copy } from '../copy/en';
import { rupees } from '../util/money';
import {
  buildPayload,
  decodePayload,
  expandImage,
  type QrPayload,
} from '../util/qrpayload';
import css from './buyer.module.css';

/**
 * What a scanned QR opens.
 *
 * The usual case is `?p=`: everything comes out of the URL, so this page
 * renders with no backend at all. That is deliberate — a judge scanning the
 * code at a stall should not depend on a sleeping Space waking up in time.
 *
 * `?listing=` is the overflow case. A payload too big for a scannable symbol
 * falls back to an id, which does need the backend, so it is fetched here.
 *
 * The payload arrives from a query string, so it is untrusted input — it is
 * shape-checked on decode and rendered as text, never as markup.
 */
export function BuyerView({ encoded, listingId }: { encoded?: string; listingId?: string }) {
  if (listingId) return <FetchedProduct id={listingId} />;

  const payload = encoded ? decodePayload(encoded) : null;
  if (!payload) return <Message text="This link is incomplete, so the product cannot be shown." />;
  return <Page payload={payload} />;
}

/** The `?listing=` path: one fetch, then the same rendering as `?p=`. */
function FetchedProduct({ id }: { id: string }) {
  const [payload, setPayload] = useState<QrPayload | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    void (async () => {
      try {
        const listing = await api.listing(id, controller.signal);
        setPayload(
          buildPayload(
            listing,
            listing.fact_sheet.price_in_paise ?? listing.suggested_price_in_paise,
            listing.image_urls.map((u) => api.mediaUrl(u)),
          ),
        );
      } catch {
        if (!controller.signal.aborted) setFailed(true);
      }
    })();
    return () => controller.abort();
  }, [id]);

  if (failed) {
    return <Message text="This product could not be loaded. The link may have expired." />;
  }
  if (!payload) return <Message text="Loading the product…" />;
  return <Page payload={payload} />;
}

function Message({ text }: { text: string }) {
  return (
    <div className={css.page}>
      <p className={css.empty}>{text}</p>
    </div>
  );
}

function Page({ payload }: { payload: QrPayload }) {
  return (
    <div className={css.page}>
      <div className={css.inner}>
        <Content payload={payload} />
      </div>
    </div>
  );
}

function Content({ payload }: { payload: QrPayload }) {
  // Images travel as "~listingId/mediaId" to keep the QR sparse enough to
  // scan; the origin is put back here.
  const images = payload.i.map((ref) => expandImage(ref, API_BASE));
  const [hero, ...rest] = images;

  return (
    <>
      <p className={css.brand}>Kirtikar</p>

      {hero ? <Photo className={css.hero} src={hero} alt={payload.t} /> : null}

      {rest.length ? (
        <div className={css.thumbs}>
          {rest.map((url) => (
            <Photo className={css.thumb} key={url} src={url} alt="" />
          ))}
        </div>
      ) : null}

      <h1 className={css.title}>{payload.t}</h1>
      <p className={css.price}>{payload.p != null ? rupees(payload.p) : copy.listingNoPrice}</p>
      {payload.d ? <p className={css.desc}>{payload.d}</p> : null}

      {payload.f.length ? (
        <div className={css.facts}>
          {payload.f.map(([label, value]) => (
            <div key={label} style={{ display: 'contents' }}>
              <span className={css.factLabel}>{label}</span>
              <span className={css.factValue}>{value}</span>
            </div>
          ))}
        </div>
      ) : null}

      <p className={css.footer}>
        Listed with Kirtikar — photographs, description and price generated from one
        photo and a spoken sentence.
        <br />
        <a href={import.meta.env.BASE_URL}>Try it yourself</a>
      </p>
    </>
  );
}

/**
 * Photos live on the backend even when the text came out of the URL, so a
 * sleeping Space means a broken-image icon over an otherwise complete
 * product. Dropping the element instead leaves the page looking deliberate.
 */
function Photo({ className, src, alt }: { className?: string; src: string; alt: string }) {
  const [broken, setBroken] = useState(false);
  if (broken) return null;
  return <img className={className} src={src} alt={alt} onError={() => setBroken(true)} />;
}
