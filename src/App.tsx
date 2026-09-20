import { Stage } from './stage/Stage';
import { ProductRail } from './stage/ProductRail';
import { ExplainerPanel } from './stage/ExplainerPanel';
import { BackendChip } from './stage/BackendChip';
import { DemoApp } from './app/DemoApp';
import { BuyerView } from './buyer/BuyerView';
import { Intro } from './intro/Intro';

export function App() {
  // The QR's buyer page renders full-bleed: a buyer scanning the code is
  // already holding a phone, so wrapping it in a picture of one is absurd.
  const params = new URLSearchParams(window.location.search);
  const payload = params.get('p');
  const listingId = params.get('listing');
  if (payload || listingId) {
    return <BuyerView encoded={payload ?? undefined} listingId={listingId ?? undefined} />;
  }

  // The stage is mounted from the first frame even though the intro covers
  // it, so BackendChip's health watcher starts waking a sleeping Space while
  // the visitor is still looking at the logo.
  return (
    <Intro>
      <Stage
        aside={<ProductRail />}
        panel={
          <>
            <BackendChip />
            <ExplainerPanel />
          </>
        }
      >
        <DemoApp />
      </Stage>
    </Intro>
  );
}
