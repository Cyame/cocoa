import { createBrowserRouter } from 'react-router';
import App from '../App';

function Index() {
  return <div>Cocoa Portal</div>;
}

const router = createBrowserRouter([
  {
    path: '/',
    Component: App,
    children: [{ index: true, Component: Index }],
  },
]);

export default router;
