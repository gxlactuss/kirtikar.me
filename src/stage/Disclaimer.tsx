import css from './stage.module.css';

/**
 * Says plainly what the demo is and is not. A judge with no one beside them
 * could otherwise take the phone on the desk for the shipped app, when it is
 * a window onto the pipeline alone.
 */
export function Disclaimer() {
  return (
    <aside className={css.disclaimer}>
      <p className={css.pickerTitle}>About this demo</p>
      <p className={css.disclaimerBody}>
        This is not a recreation of the Kirtikar app. It is a demo of the raw
        processing on this website: one photo and one voice note in, one listing
        out.
      </p>
      <p className={css.disclaimerBody}>
        The app itself considers more parameters and asks the seller for more
        feedback along the way.
      </p>
    </aside>
  );
}
