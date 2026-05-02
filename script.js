document.addEventListener('DOMContentLoaded', () => {
    // Add scroll effect to navbar
    const navbar = document.getElementById('navbar');
    
    window.addEventListener('scroll', () => {
        if (window.scrollY > 50) {
            navbar.style.background = 'rgba(15, 23, 42, 0.95)';
            navbar.style.boxShadow = '0 4px 20px rgba(0, 0, 0, 0.3)';
        } else {
            navbar.style.background = 'rgba(15, 23, 42, 0.8)';
            navbar.style.boxShadow = 'none';
        }
    });

    // Add interactive click effects
    const buttons = document.querySelectorAll('button');
    
    buttons.forEach(btn => {
        btn.addEventListener('click', function(e) {
            let x = e.clientX - e.target.offsetLeft;
            let y = e.clientY - e.target.offsetTop;
            
            let ripples = document.createElement('span');
            ripples.style.left = x + 'px';
            ripples.style.top = y + 'px';
            ripples.style.position = 'absolute';
            ripples.style.background = 'rgba(255,255,255,0.3)';
            ripples.style.width = '20px';
            ripples.style.height = '20px';
            ripples.style.transform = 'translate(-50%, -50%)';
            ripples.style.borderRadius = '50%';
            ripples.style.pointerEvents = 'none';
            ripples.style.animation = 'animate 1s linear';
            
            // Add required styles for ripple effect dynamically if needed
            if(getComputedStyle(this).position === 'static') {
                this.style.position = 'relative';
            }
            this.style.overflow = 'hidden';
            
            this.appendChild(ripples);
            
            setTimeout(() => {
                ripples.remove()
            }, 1000);
            
            // Dummy logic for prototype
            if(this.id === 'aiStylistBtn') {
                alert("Initiating AI Stylist capabilities... (Mockup)");
            }
        });
    });
});

// Adding ripple animation dynamically to document
const style = document.createElement('style');
style.innerHTML = `
    @keyframes animate {
        0% {
            width: 0px;
            height: 0px;
            opacity: 0.5;
        }
        100% {
            width: 500px;
            height: 500px;
            opacity: 0;
        }
    }
`;
document.head.appendChild(style);
