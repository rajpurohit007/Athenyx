import React from 'react'
import './Services.css'
import { Helmet } from 'react-helmet'
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import { faWindowMaximize } from '@fortawesome/free-regular-svg-icons';
import { faMobileScreenButton } from '@fortawesome/free-solid-svg-icons';
import { faFigma } from '@fortawesome/free-brands-svg-icons';
import { faCloudflare } from '@fortawesome/free-brands-svg-icons';
import { faHeadset } from '@fortawesome/free-solid-svg-icons';
import { faBullhorn } from '@fortawesome/free-solid-svg-icons';

const Services = () => {
  return (
    <>
     <Helmet>
          <title>Services | Athenyx</title>
          <meta name='description' content="Software company provide SAAS service." />
          <meta name='keywords' content='Athenyx, software company, IT , Software as a service, SAAS, get your software ,services, IT services , athenyx service'/>
        </Helmet>
     <div className='services' id='services'>
        <div className='service-header'>
            <h2>Services</h2>
        </div>
        <div className='service-cards'>
            <div class="container">
                <div class="row g-2">
                   <div class="col-12 col-md-4">
                        <div class="p-3 border bg-light">
                            <div class="card" >
                                <a className="service-icons" href="#"  rel="noopener noreferrer">
                                    <FontAwesomeIcon icon={faWindowMaximize} />
                                </a>
                                <h3>Web Development</h3>
                                <p class="card-text">We build fast, responsive, and modern websites that look great, work flawlessly on all devices, and help grow your business online.</p>
                            </div>
                        </div>
                    </div>
               <div class="col-12 col-md-4">
                        <div class="p-3 border bg-light">
                            <div class="card" >
                                <a className="service-icons" href="#"  rel="noopener noreferrer">
                                    <FontAwesomeIcon icon={faMobileScreenButton} />
                                </a>
                                <h3>App  Development</h3>
                                <p class="card-text">We craft sleek, high-performance mobile apps that run smoothly on all devices, deliver seamless experiences, and grow your business.</p>
                            </div>
                        </div>
                    </div>
                <div class="col-12 col-md-4">
                        <div class="p-3 border bg-light">
                            <div class="card" >
                                <a className="service-icons" href="#"  rel="noopener noreferrer">
                                    <FontAwesomeIcon icon={faFigma} />
                                </a>
                                <h3>Graphic, UI/UX Design</h3>
                                <p class="card-text">We craft beautiful, user-friendly designs that captivate and engage, enhancing your brand and delivering seamless experiences.</p>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
            <div class="container">
                <div class="row g-2">
                   <div class="col-12 col-md-4">
                        <div class="p-3 border bg-light">
                            <div class="card" >
                                <a className="service-icons" href="#"  rel="noopener noreferrer">
                                    <FontAwesomeIcon icon={faCloudflare} />
                                </a>
                                <h3>Hosting Service</h3>
                                <p class="card-text">We provide reliable, fast, and secure hosting solutions that ensure your website runs smoothly, performs at its best, and stays online 24/7 customer support.</p>
                            </div>
                        </div>
                    </div>
               <div class="col-12 col-md-4">
                        <div class="p-3 border bg-light">
                            <div class="card" >
                                <a className="service-icons" href="#"  rel="noopener noreferrer">
                                    <FontAwesomeIcon icon={faHeadset} />
                                </a>
                                <h3>Maintenance & Support</h3>
                                <p class="card-text">We provide reliable, ongoing maintenance and expert support to keep your systems secure and updated.</p>
                            </div>
                        </div>
                    </div>
                <div class="col-12 col-md-4">
                        <div class="p-3 border bg-light">
                            <div class="card" >
                                <a className="service-icons" href="#"  rel="noopener noreferrer">
                                    <FontAwesomeIcon icon={faBullhorn} />
                                </a>
                                <h3>Digital Marketing</h3>
                                <p class="card-text">We help your brand grow online with smart strategies, targeted campaigns, SEO, and social media marketing that drive traffic, boost engagement, and deliver real results.</p>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>
    </>
   
  )
}

export default Services