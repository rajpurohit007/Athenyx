import React from 'react'
import { Helmet } from 'react-helmet'
import './About.css'
import logo from './images/about-img.png'
import logo2 from './images/company_logo.jpg'
const About = () => {
  return (
    <div className='about' id='about'>
        <div className='about-header'>
            <h2>About Us</h2>
        </div>
        <div class="container overflow-hidden">
            <div class="row gx-5">
                <div class="col col-img">
                    <div class="p-3  about-img">
                        <img src={logo2} alt='company_logo'></img>
                        {/* <h3>We're <span> Athenyx </span></h3> */}
                        {/* <p>A new tech company founded in 2025.we create innovative digital solution for morden business.</p> */}
                        {/* <p>Founded in 2025, we are a next-generation tech company focused on crafting innovative digital solutions that empower modern businesses. Our expertise spans custom website and mobile app development, UI/UX design, hosting, digital marketing, and robust backend systems. Whether you're a startup or an enterprise, we build fast, scalable, and visually engaging digital products that work seamlessly across all devices.</p> */}
                    </div>
                </div>
                <div class="col">
                    <div class="p-3 about-content">
                        <h3>We're <span> Athenyx </span></h3>
                        <p>A new tech company founded in 2025.we create innovative digital solution for morden business.</p>
                        {/* <h4>What We Do & How We Work 🚀</h4> */}
                        {/* <p>We build websites, mobile apps, and custom software that help businesses grow, combining creativity with functionality. Our process is simple and transparent—we communicate clearly, focus on your goals, and deliver results on time, every time.</p> */}
                    </div>
                    <div class="p-3 about-content">
                         <h4>What We Do 💡</h4>
                        <p>We build website, mobile app and custom software that helps businesses grow. </p>
                    </div>
                    <div class="p-3 about-content">
                        <h4>How We Work 🚀</h4>
                        <p>We keep things simple, communicate clearly, and deliver result on time. </p>
                    </div>
                </div>
            </div>
        </div>
    </div>
  )
}

export default About