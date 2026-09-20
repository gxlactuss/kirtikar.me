import { Stage } from './stage/Stage';
import { ProductRail } from './stage/ProductRail';
import { DemoApp } from './app/DemoApp';
import { BuyerView } from './buyer/BuyerView';
import { Intro } from './intro/Intro';
import { ShellBar } from './shell/ServerStatus';

export function App() {
  // The QR's buyer page renders full-bleed: a buyer scanning the code is
  // already holding a phone, so wrapping it in a picture of one is absurd.
  const params = new URLSearchParams(window.location.search);
  const payload = params.get('p');
  const listingId = params.get('listing');
  if (payload || listingId) {
    // The buyer page is app surface and stays cream in both themes, so the
    // bar floating over it is pinned to the light set rather than the
    // visitor's stage theme.
    return (
      <div className="lightStage">
        <ShellBar />
        <BuyerView encoded={payload ?? undefined} listingId={listingId ?? undefined} />
      </div>
    );
  }

  // ShellBar sits outside the intro on purpose. It is the same bar on every
  // page, and it owns the health watcher — so a sleeping Space has been
  // waking since the first frame, while the visitor is still on the logo.
  return (
    <>
      <ShellBar />
      <Intro>
        <Stage aside={<ProductRail />}>
          <DemoApp />
        </Stage>
      </Intro>
    </>
  );
}
