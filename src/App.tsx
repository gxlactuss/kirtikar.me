import { Stage } from './stage/Stage';
import { DemoApp } from './app/DemoApp';
import { Intro } from './intro/Intro';
import { ShellBar } from './shell/ServerStatus';

export function App() {
  // ShellBar sits outside the intro on purpose. It is the same bar on every
  // page, and it owns the health watcher — so a sleeping server has been
  // waking since the first frame, while the visitor is still on the logo.
  return (
    <>
      <ShellBar />
      <Intro>
        <Stage>
          <DemoApp />
        </Stage>
      </Intro>
    </>
  );
}
