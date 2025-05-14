import React from 'react'
import './Hero.css'
import hero_image from './images/hero_background.jpg'
import { Helmet } from 'react-helmet'

const Hero = () => {
  return (

    <>
    <Helmet>
      <title>Home | Athenyx</title>
      <meta name='description' content="Software company provide SAAS service." />
      <meta name='keywords' content='Athenyx, software company, IT , Software as a service, SAAS, get your software'/>
    </Helmet>
      <div className='hero' id='hero'>
        {/* <div className='box1 box'></div>
        <div className='box2 box'></div> */}
        <div className='hero-left'>
          <h1>Think Big. 
            <br />We make IT, possible!</h1>
            <h2>Take your business online</h2>
          <div className='button'> 
          <a href="https://wa.me/9825964861" target="_blank" rel="noopener noreferrer">
            <button className='Button_contact wp'>WhatsApp</button>
          </a>

          <a href="mailto:athenyx4800@gmail.com">
            <button className='Button_contact mail'>Mail</button>
          </a>

          </div>
        </div>
        <div className='hero-right'>
          <img src={hero_image} alt='hero_image'></img>

        </div>

    </div>
    </>
   
  )
}

export default Hero