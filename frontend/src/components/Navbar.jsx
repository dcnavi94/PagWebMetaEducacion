import { useNavigate, useLocation } from 'react-router-dom';
import parse, { attributesToProps, domToReact } from 'html-react-parser';
import { navHtml } from './navbarContent';

const Navbar = () => {
  const navigate = useNavigate();

  const options = {
    replace: (domNode) => {
      if (domNode.name === 'a' && domNode.attribs && domNode.attribs.href) {
        const href = domNode.attribs.href;
        
        if (href.startsWith('http') || href.startsWith('mailto:') || href.startsWith('tel:') || href.startsWith('https://wa.me')) {
          return;
        }

        return (
          <a
            {...attributesToProps(domNode.attribs)}
            onClick={(e) => {
              e.preventDefault();
              navigate(href);
            }}
          >
            {domNode.children ? domToReact(domNode.children, options) : null}
          </a>
        );
      }
    }
  };

  return (
    <>
      {parse(navHtml, options)}
    </>
  );
};

export default Navbar;
