import { useEffect, useRef, useState } from 'react';
import QRCode from 'qrcode';

import { api } from '../../api/client';
import { copy } from '../../copy/en';
import { dispatch, useDemo } from '../../machine/store';
import { buyerUrl } from '../../util/qrpayload';
import { BigActionButton } from '../widgets/BigActionButton';
import { Scaffold } from '../widgets/Scaffold';
import { ScreenHeader } from '../widgets/ScreenHeader';
import { SuccessMark } from '../widgets/SuccessMark';
import { Panel } from './Panel';
import css from './review.module.css';

type Phase = 'publishing' | 'published' | 'failed';

/**
 * The last screen: pushes the edits, publishes, then shows the QR.
 *
 * Edits are sent here rather than as the seller makes them, so a flaky
 * network never interrupts the wizard. A failed PATCH does not fail the
 * publish — the listing still goes up, just without that one correction,
 * which is the right trade for a seller on a village connection.
 */
export function PublishStage() {
  const { listing, priceInPaise, quantity, isOneOfAKind, consent, photoOrder, provenance } =
    useDemo();
  const [phase, setPhase] = useState<Phase>('publishing');
  const [qr, setQr] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const linkRef = useRef<string>('');
  const ran = useRef(false);

  useEffect(() => {
    if (!listing || ran.current) return;
    ran.current = true;

    void (async () => {
      const live = provenance?.kind === 'live';

      if (live) {
        try {
          await api.patch(listing.id, {
            price: priceInPaise,
            quantity: isOneOfAKind ? 1 : quantity,
            isOneOfAKind,
          });
        } catch {
          // Keep going: the correction is lost, the listing is not.
        }
        try {
          await api.consent(listing.id, consent.photo, consent.story);
          await api.publish(listing.id);
        } catch {
          setPhase('failed');
          return;
        }
      } else {
        // Replayed run: there is no server-side listing to publish against.
        await new Promise((r) => setTimeout(r, 1400));
      }

      const ordered = photoOrder
        .map((i) => listing.image_urls[i])
        .filter((u): u is string => Boolean(u));
      const url = buyerUrl(
        window.location.origin,
        listing,
        priceInPaise,
        consent.photo ? ordered.map((u) => api.mediaUrl(u)) : [],
      );
      linkRef.current = url;

      try {
        setQr(
          await QRCode.toDataURL(url, {
            width: 480,
            margin: 1,
            // L, not M: this code is displayed on a screen, not printed on a
            // label that might get scuffed. The lower level buys a smaller
            // symbol, which matters far more for scanning off a 240px box.
            errorCorrectionLevel: 'L',
            color: { dark: '#3A2415', light: '#FFFFFF' },
          }),
        );
      } catch {
        // A listing without a QR is still published; just show the link.
      }
      setPhase('published');
    })();
  }, [listing, priceInPaise, quantity, isOneOfAKind, consent, photoOrder, provenance]);

  if (!listing) return null;

  if (phase === 'publishing') {
    return (
      <Scaffold>
        <ScreenHeader title={copy.publishingTitle} subtitle={copy.publishingBody} />
        <div className={css.publishCentre}>
          <span className={css.spinnerBig} />
        </div>
      </Scaffold>
    );
  }

  if (phase === 'failed') {
    return (
      <Scaffold
        actions={
          <BigActionButton
            label={copy.publishRetry}
            icon="refresh"
            onClick={() => {
              ran.current = false;
              setPhase('publishing');
            }}
          />
        }
      >
        <ScreenHeader title={copy.publishFailed} />
        <div className={css.publishCentre}>
          <SuccessMark icon="error_outline" tone="danger" />
        </div>
      </Scaffold>
    );
  }

  return (
    <Scaffold
      pill={provenance?.kind === 'fixture' ? copy.demo.demoDataPill : null}
      actions={
        <>
          <BigActionButton
            label={copy.publishedShare}
            icon="share"
            onClick={() => {
              const text = `${listing.title ?? ''} — ${linkRef.current}`;
              window.open(
                `https://wa.me/?text=${encodeURIComponent(text)}`,
                '_blank',
                'noopener',
              );
            }}
          />
          <BigActionButton
            label={copied ? copy.publishedLinkCopied : copy.publishedCopyLink}
            icon="link"
            tone="secondary"
            onClick={() => {
              void navigator.clipboard?.writeText(linkRef.current);
              setCopied(true);
              setTimeout(() => setCopied(false), 2000);
            }}
          />
          <BigActionButton
            label={copy.publishedAnother}
            icon="add"
            tone="secondary"
            onClick={() => dispatch({ t: 'reset' })}
          />
        </>
      }
    >
      <ScreenHeader title={copy.publishedTitle} subtitle={copy.publishedBody} />

      <div className={css.publishCentre}>
        <SuccessMark />
        {qr ? (
          <div className={css.qrBox}>
            <img src={qr} alt="Scan to open this product" />
          </div>
        ) : null}
        <Panel tone="success">{copy.publishedQrExplain}</Panel>
      </div>
    </Scaffold>
  );
}
