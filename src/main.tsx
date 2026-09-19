import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';

import './app/theme/tokens.css';
import './app/theme/reset.css';
import './app/theme/type.css';

import { App } from './App';

const host = document.getElementById('root');
if (!host) throw new Error('#root is missing from index.html');

createRoot(host).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
