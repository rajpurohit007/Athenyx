import React from 'react'
import './Footer.css'
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import { faEnvelope } from '@fortawesome/free-solid-svg-icons';
import {
  faInstagram,
  faFacebook,
  faLinkedin,
  faWhatsapp
} from '@fortawesome/free-brands-svg-icons';

const Footer = () => {
  return (
    <div className='footer' id='footer'>
        <div className='footer-top '>
            {/* <div className='footer-left'>
                <h2>ATHENYX</h2>
                <p>B-222, Jeram Morar ni Vadi, Hariom Society, Katargam, Surat, Gujarat 395004</p>
                <a className="footer-icons" href="https://instagram.com" target="_blank" rel="noopener noreferrer">
                    <FontAwesomeIcon icon={faInstagram} />
                </a>

                <a className="footer-icons" href="https://facebook.com" target="_blank" rel="noopener noreferrer">
                    <FontAwesomeIcon icon={faFacebook} />
                </a>

                <a className="footer-icons" href="https://linkedin.com" target="_blank" rel="noopener noreferrer">
                    <FontAwesomeIcon icon={faLinkedin} />
                </a>

                <a className="footer-icons" href="https://wa.me/1234567890" target="_blank" rel="noopener noreferrer">
                    <FontAwesomeIcon icon={faWhatsapp} />
                </a>

                <a className="footer-icons" href="mailto:someone@example.com">
                    <FontAwesomeIcon icon={faEnvelope}  />
                </a>
            </div>
            <div className='footer-right'>
                <div className='footer-right'>
                <h6>Quick Links</h6>
                <ul className='navbar-nav me-auto mb-2 mb-lg-0'>
                    <li><a href='#'>Home</a></li>
                    <li><a href='#'>Services</a></li>
                    <li><a href='#'>About</a></li>
                    <li><a href='#'>Contact</a></li>
                </ul>
                </div>
                <div className='footer-right'>
                <h6>Contact Info</h6>
                <ul className='navbar-nav me-auto mb-2 mb-lg-0'>
                    <li><p>Email: info@company.com</p></li>
                    <li><p>Phone: +91 9876543210</p></li>
                </ul>
                </div>
                
            </div>  */}
            <div class="container">
  <div class="row g-2 flex-row">
    <div class="col-12 col-md-6">
      <div class="p-3 ">
        <div className='footer-left'>
                <h2>ATHENYX</h2>
                <p>B-222, Jeram Morar ni Vadi, Hariom Society, Katargam, Surat, Gujarat 395004</p>
                <a className="footer-icons" href="https://www.instagram.com/athenyx_/" target="_blank" rel="noopener noreferrer">
                    <FontAwesomeIcon icon={faInstagram} />
                </a>

                {/* <a className="footer-icons" href="https://facebook.com" target="_blank" rel="noopener noreferrer">
                    <FontAwesomeIcon icon={faFacebook} />
                </a>

                <a className="footer-icons" href="https://linkedin.com" target="_blank" rel="noopener noreferrer">
                    <FontAwesomeIcon icon={faLinkedin} />
                </a> */}

                <a className="footer-icons" href="https://wa.me/9825964861" target="_blank" rel="noopener noreferrer">
                    <FontAwesomeIcon icon={faWhatsapp} />
                </a>

                <a className="footer-icons" href="mailto:athenyx4800@gmail.com" >
                    <FontAwesomeIcon icon={faEnvelope}  />
                </a>
            </div>
      </div>
    </div>
    <div class="col-0 col-md-3">
      {/* <div class="p-3">
        <div className='footer-right'>
                <h6>Contact Info</h6>
                <ul className='navbar-nav me-auto mb-2 mb-lg-0'>
                    <li><p>Email: info@company.com</p></li>
                    <li><p>Phone: +91 9876543210</p></li>
                </ul>
                </div>
      </div> */}
    </div>
    {/* <div class="col-12 col-md-2">
      <div class="p-3">
        <div className='footer-right'>
                <h6>Quick Links</h6>
                <ul className='navbar-nav me-auto mb-2 mb-lg-0'>
                    <li><a href='#'>Home</a></li>
                    <li><a href='#'>Services</a></li>
                    <li><a href='#'>About</a></li>
                    <li><a href='#'>Contact</a></li>
                </ul>
                </div>
      </div>
    </div> */}
   <div class="col-12 col-md-3">
      <div class="p-3">
        <div className='footer-right'>
                <h6>Contact Info</h6>
                <ul className='navbar-nav me-auto mb-2 mb-lg-0'>
                    <li><p>Email: athenyx4800@gmail.com</p></li>
                    <li><p>Phone: +91 9825964861</p></li>
                </ul>
                </div>
      </div>
    </div>
  </div>
</div>
        </div>
        
        <div className='footer-bottom'>
            &copy; -2025 Copyright reserved by Athenyx.
        </div>
    </div>
  )
}

export default Footer